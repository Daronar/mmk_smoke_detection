import datetime
from typing import Optional
import hikvisionapi as hv
from multiprocessing import get_logger as m_get_logger
import numpy as np
import threading
import logging
import time
import re
import cv2
import os

DEFAULT_CHUNK_SIZE = 17000
TIME_FORMAT = "%m/%d/%Y_%H:%M:%S"
DEFAULT_FORMAT = ".jpg"

def parse_url(to_parse: str):
    user = re.search(r'//[a-z0-9A-Z]*:', to_parse)[0].replace("//", "").replace(":", "")
    password = re.search(r':[a-z0-9A-Z!]*@', to_parse)[0].replace("@", "").replace(":", "")
    ip = re.search(r'[0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,4}', to_parse)[0]
    return ip, user, password



def get_logger(level=logging.INFO) -> logging.Logger:
    logger = m_get_logger()
    formatter = logging.Formatter("%(asctime)s]:[%(name)s]:{%(levelname)s}:%(message)s")
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(level)
    return logger

class CamReader(threading.Thread):
    """
        Класс для непрерывного чтения в потоке
    """
    _stream: cv2.VideoCapture
    _logger: logging.Logger
    _frame: Optional = None
    _stamp: float = 0
    _address: str
    _reconnect_counter: int = 0
    _fps: int

    def __init__(self,
                 address: str, name: str, logger: logging.Logger,
                 fps: int = 12) -> None:
        super().__init__(name=name)
        self._logger = logger
        self._address = address
        self._fps = fps

    def _connect(self) -> None:
        self._logger.info(f"[{self.name}]::_connect: Connecting to the camera [], "
                          f"with buffer size [{cv2.CAP_PROP_BUFFERSIZE}],"
                          f"and fps [{self._fps}]")
        self._stream = cv2.VideoCapture(self._address)
        self._stream.set(cv2.CAP_PROP_FPS, self._fps)
        self._stream.set(cv2.CAP_PROP_BUFFERSIZE, 2)
        self._logger.info(
            f"[{self.name}]::_connect:Connect success to the camera stream {self._address}")

    def reconnect(self):
        self._stream = cv2.VideoCapture(self._address)
        self._stream.set(cv2.CAP_PROP_FPS, self._fps)
        self._stream.set(cv2.CAP_PROP_BUFFERSIZE, 2)
        self._logger.info(
            f"[{self.name}]::_connect:ReConnect success to the camera stream {self._address}")

    def run(self) -> None:
        self._logger.info(f"[{self.name}]::_connect: Starting streaming")
        self._connect()
        while True:
            _, frame = self._stream.read()
            if isinstance(frame, np.ndarray):
                self._frame = frame
                self._stamp = time.time()
                if self._reconnect_counter > 100:
                    self.reconnect()
                    self._reconnect_counter = 0
            elif frame is None and self._reconnect_counter > 100:
                self._connect()
                self._reconnect_counter = 0
            elif frame is None:
                self._logger.debug(f"[{self.name}]::run:Camera stream is empty")
                self._reconnect_counter += 1
            else:
                self._logger.warning(f"[{self.name}]::run: Unsupported situation!")

    def get_frame(self):
        self._reconnect_counter += 1
        return self._frame, self._stamp



class HyperCamReader(threading.Thread):
    _reconnect_counter = 0
    _camera: hv.hikvisionapi.Client
    _logger: logging.Logger
    _frame: Optional = None
    _stamp: float = 0
    _address: str
    _fps: int
    _save_folder: str
    _ip: str = ""

    def __init__(self, address: str, name: str, logger: logging.Logger, save_folder: str):
        super().__init__(name=name)
        self._logger = logger
        self._address = address
        self._prepare_folder(save_folder)

    def connect(self):
        ip, user, password = parse_url(self._address)
        self._logger.info(
            f"[{self.name}]::_connect connecting to the IP [http://{ip}], USER [{user}],PSWD [{password}]")
        self._camera = hv.Client(f'http://{ip}', user, password)

        self._logger.info(
            f"[{self.name}]::_connect:Connect success to the camera stream {self._address} "
            f"and device {self._camera.System.deviceInfo(method='get')}")

    def run(self) -> None:
        self.connect()
        while True:
            stream = self._camera.Streaming.channels[101].picture(method='get', type='opaque_data')
            body = b''
            for chunk in stream.iter_content(chunk_size=DEFAULT_CHUNK_SIZE):
                body += chunk
                start = body.find(b'\xff\xd8')
                end = body.find(b'\xff\xd9')
                if start != -1 and end != -1:
                    img = body[start:end + 2]
                    body = body[end + 2:]
                    self._save_frame(cv2.imdecode(
                        np.fromstring(img, dtype=np.uint8), cv2.IMREAD_COLOR), datetime.datetime.now()
                    )

    def _prepare_folder(self, path: str):
        ip, user, password = parse_url(self._address)
        self._ip = ip
        try:
            if not os.path.exists(os.path.join(path, ip)):
                os.mkdir(os.path.join(path, ip))
            self._save_folder = os.path.join(path, ip)
        except FileExistsError:
            self._save_folder = os.path.join(os.getcwd(), ip)
            os.mkdir(self._save_folder)
        self._logger.info(
            f"[{self.name}]::_prepare_folder: Save folder for cam [{ip}] > [{self._save_folder}]")

    def _save_frame(self, frame: np.ndarray, timestamp: datetime.datetime):
        file_name = f"frame_[{timestamp.strftime(TIME_FORMAT)}]_IP[{self._ip}.jpg]"
        filepath = os.path.join(self._save_folder, file_name)
        cv2.imwrite(filepath, frame)


if __name__ == '__main__':
    log = get_logger(logging.INFO)
    recorders = [
        "rtsp://root:Video5000@172.30.71.99/ISAPI/Streaming/Channels/101",
        "rtsp://root:Video5000@172.30.71.100/ISAPI/Streaming/Channels/101",
        "rtsp://root:Video5000@172.30.71.101/ISAPI/Streaming/Channels/101",
        "rtsp://root:Video5000@172.30.71.102/ISAPI/Streaming/Channels/101",
        "rtsp://root:Video5000@172.30.71.103/ISAPI/Streaming/Channels/101",
        "rtsp://root:Video5000@172.30.71.104/ISAPI/Streaming/Channels/101",
        "rtsp://root:Video5000!@172.30.71.105/ISAPI/Streaming/Channels/101",
        "rtsp://root:Video5000!@172.30.71.106/ISAPI/Streaming/Channels/101",
        "rtsp://root:Video5000!@172.30.71.107/ISAPI/Streaming/Channels/101",
        "rtsp://root:Video5000!@172.30.71.108/ISAPI/Streaming/Channels/101",
        "rtsp://root:Video5000!@172.30.71.109/ISAPI/Streaming/Channels/101",
        "rtsp://root:Video5000!@172.30.71.110/ISAPI/Streaming/Channels/101",
    ]
    SAVE_FOLDER = "D:\\smoke_dataset"
    recs = [HyperCamReader(
        name=f"Cam_writer_{(itt+100)-1}",
        logger=log,
        address=cam,
        save_folder=SAVE_FOLDER
    ) for itt, cam in enumerate(recorders)]
    for rec in recs:
        rec.start()
    for rec in recs:
        re