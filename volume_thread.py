import time

import serial
import utils
from pathlib import Path
from control import Control

from PyQt5.QtCore import QThread
from PyQt5.QtWidgets import QMessageBox

logger = utils.get_logger()


class VolumeThread(QThread):
    def __init__(self, mapping_dir=None):
        super().__init__()
        logger.info("Creating volume thread.")
        self.running = True
        self.control = Control(Path.cwd() / 'mapping.txt')
        logger.info("Setting up serial communication.")
        try:
            self.arduino = serial.Serial(self.control.port, self.control.baudrate, timeout=0.1)
            logger.info(self.arduino)
        except serial.SerialException:
            QMessageBox.critical(
                None,
                "Application already running",
                "The application crashed because the serial connection is busy. This may mean "
                "that another instance is already running. Please check the system tray or the "
                "task manager.",
            )
            raise

    def run(self):
        logger.info("Entering thread loop.")
        while self.running:
            if self.control.sessions is not None:
                try:
                    if self.arduino is None:
                        self.arduino = serial.Serial(self.control.port, self.control.baudrate, timeout=0.1)
                        logger.info("Reconnected, " + str(self.arduino))
                    # Data is formatted as "<val>|<val>|<val>|<val>|<val>?<micmute>"
                    data = str(self.arduino.readline()[:-2], "utf-8")  # Trim off '\r\n'.
                    if data:
                        try:
                            values = [float(val) for val in data.split("?")[0].split("|")]
                            self.control.set_volume(values)
                            if data.split("?")[1]:
                                self.control.mute_mic(bool(int(data.split("?")[1])))
                        except Exception as e:
                            logger.warning(f"Error processing volume data: {e}")
                except serial.SerialException:
                    if not (self.arduino is None):
                        self.arduino.close()
                        self.arduino = None
                        logger.info("Disconnected")

                    logger.info("No Connection")
                    time.sleep(1)
