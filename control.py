from pathlib import Path

from pulsectl import PulseError
from serial.tools import list_ports

import utils
from sessions import SessionGroup, Master, Session
import re
import pulsectl

logger = utils.get_logger()


class Control:
    """
    Contains all the fields necessary to control the audio sessions. It is responsible for parsing the config file,
    and harbours the sessions so that they can be accessed as needed.
    """

    def __init__(self, path=None):
        self.path = (self.get_config_file_path() / 'LiVeS' / 'mapping.txt') if path is None else path

        # Check if there is a custom mapping directory specified in config.yaml. If not, use %appdata%.
        mapping_dir = utils.get_mapping_dir()
        if mapping_dir is None or mapping_dir == "":
            self.mapping_dir = utils.get_appdata_path() / "mapping.txt"
            utils.save_mapping_dir(self.mapping_dir.as_posix())
        else:
            self.mapping_dir = Path(mapping_dir)

        print(self.mapping_dir)
        self.sessions = None
        self.port = None
        self.baudrate = None
        self.inverted = False
        self.unmapped = []
        self.pulse = pulsectl.Pulse('LiVeS')
        self.sink_number = len(self.pulse.sink_input_list())

        self.load_config()  # Read the mappings from mapping.txt

        self.sliders = int(self.get_setting("sliders"))
        self.port = self.get_port()
        self.baudrate = self.get_setting("baudrate")
        self.inverted = self.get_setting("inverted").lower() == "true"

        self.get_mapping()

    def load_config(self):
        """
        Read the mapping text file and split the lines.
        """
        self.lines = self.mapping_dir.read_text().split("\n")

    def get_setting(self, text):
        """
        Finds a line from the config file that contains "text".
        E.g. get_setting("0") will get the application that is set to the first slider, and get_setting("port")
        will get the port value from the config.
        :param text: Text that is to be found, like "port" or "baudrate"
        :return: The first element in the config file that contains "text", if any.
        """
        setting = list(filter(lambda x: text + ":" in x, self.lines))[0]
        return re.sub(r"^[a-zA-Z0-9]*: *", "", setting)

    def get_mapping(self):
        self.load_config()
        self.target_idxs = {}

        # For each of the sliders, get the mapping from config.txt, if it exists, and create the mapping.
        for idx in range(self.sliders):
            application_str = self.get_setting(str(idx))  # Get the settings from the config for each index.
            if "," in application_str:
                application_str = tuple(app.strip() for app in application_str.split(","))
            self.target_idxs[application_str] = int(idx)  # Store the settings in a dictionary.

        session_dict = {}
        mapped_apps = []

        # Loop through all the targets and the slider indices they are supposed to map to.
        # A target is the second part of the mapping string, after the first colon (:).
        for target, idx in self.target_idxs.items():

            # If the target is a string, it is a single target.
            if type(target) == str:
                target = target.lower()

                # If indicated with "master", create a Master volume session.
                if target == "master":
                    session_dict[idx] = Master(idx=idx, pulse=self.pulse)

                # If not indicated by "master", then consider it an application name,
                # and map only that application to the slider.
                elif target != "unmapped":  # Can be any application
                    session_dict[idx] = Session(idx, app=target, pulse=self.pulse)
                    mapped_apps.append(target)

            # If the target is a tuple, it is a group.
            elif type(target) == tuple:
                apps_in_group = []  # fmt: skip

                # Check for each application that is part of the group, if it's "master", "system" or "unmapped"
                for target_app in target:
                    target_app = target_app.lower()

                    # Exclude the other categories. Might change in the future.
                    if target_app in ["master"]:
                        continue

                    apps_in_group.append(target_app)
                    mapped_apps.append(target_app)

                # If one or more of the targeted applications are active, add a SessionGroup with them.
                if len(apps_in_group) > 0:
                    session_dict[idx] = SessionGroup(idx=idx,
                                                     pulse=self.pulse,
                                                     apps=apps_in_group)

        # Finally, if indicated with "unmapped", create a SessionGroup for all active audio session that haven't
        # been mapped before.
        if "unmapped" in self.target_idxs.keys():
            unmapped_idx = self.target_idxs["unmapped"]
            session_dict[unmapped_idx] = SessionGroup(unmapped_idx,
                                                      pulse=self.pulse,
                                                      apps=mapped_apps,
                                                      unmapped=True)

        self.sessions = session_dict

    def set_volume(self, values: list):
        try:
            for index, app in self.sessions.items():
                volume = values[index] / 1023
                if self.inverted:
                    volume = 1 - volume
                app.set_volume(volume)
            # not the best method to react to changed sinks
            if len(self.pulse.sink_input_list()) != self.sink_number:
                self.sink_number = len(self.pulse.sink_input_list())
                self.reset_volume()
        except PulseError:
            self.sink_number = len(self.pulse.sink_input_list())
            self.reset_volume()

    def mute_mic(self, muted: bool):
        for source in self.pulse.source_list():
            self.pulse.mute(source, muted)

    def reset_volume(self):
        logger.info("Resetting volume")
        for index, app in self.sessions.items():
            app.reset_volume()

    def get_port(self):
        ports = list_ports.comports()
        device_name = self.get_setting("device name")
        for port, desc, hwid in sorted(ports):
            if device_name in desc:
                return port
        else:
            try:
                return self.get_setting("port")
            except:
                raise ValueError("The config file does not contain the right device name or an appropriate port.")

    @staticmethod
    def get_config_file_path():
        """
        Returns a parent directory path where persistent application data can be stored.
        https://stackoverflow.com/questions/19078969/python-getting-appdata-folder-in-a-cross-platform-way
        """

        return Path.home() / "AppData/Roaming"
