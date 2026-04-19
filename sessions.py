from typing import List
from abc import ABC, abstractmethod
from pulsectl import Pulse, PulseObject
from statistics import median

import utils

logger = utils.get_logger()


def get_app_name(sink: PulseObject):
    name = sink.proplist.get('application.process.binary')
    if name is None:
        name = sink.proplist.get('application.name')
    if name is None:
        name = sink.proplist.get('node.name')
    if name is None:
        pass
    return name.lower()


class Base(ABC):
    def __init__(self, idx: int, pulse: Pulse):
        self.idx = idx
        self.pulse = pulse
        self.sinks = list()
        self.volume = None
        self._sink_ids = set()

    @abstractmethod
    def refresh_sinks(self):
        pass

    def set_volume(self, value):
        self.refresh_sinks()
        sink_ids = {getattr(sink, 'index', None) for sink in self.sinks}
        new_sinks = bool(self.sinks and sink_ids != self._sink_ids)

        if self.volume is None:
            self.volume = value

        # Determine whether the current sink volumes already match the desired value.
        current_volumes = [self.pulse.volume_get_all_chans(sink) for sink in self.sinks]
        volume_mismatch = any(abs(current - value) >= 0.02 for current in current_volumes)
        delta = self.volume - value

        if new_sinks or volume_mismatch or delta >= 0.02 or delta <= -0.02:
            if value >= 0.97:
                value = 1.0
            elif value <= 0.03:
                value = 0
            logger.info(
                f"apply volume: current={self.volume}, new={value}, new_sinks={new_sinks}, "
                f"mismatch={volume_mismatch}, sinks={len(self.sinks)}"
            )
            for sink in self.sinks:
                self.pulse.volume_set_all_chans(sink, value)
            self.volume = value
            self._sink_ids = sink_ids

    def reset_volume(self):
        self.refresh_sinks()
        for sink in self.sinks:
            self.pulse.volume_set_all_chans(sink, self.volume)

    def get_volume(self):
        volumes = [self.pulse.volume_get_all_chans(session) for session in self.sinks]
        if not volumes:
            return 1.0
        else:
            return median(volumes)

    def mute(self):
        for session in self.sinks:
            self.pulse.mute(session, True)

    def unmute(self):
        for session in self.sinks:
            self.pulse.mute(session, False)


class Session(Base):
    def __init__(self, idx: int, pulse: Pulse, app: str):
        self.app = app.lower()
        super().__init__(idx=idx, pulse=pulse)
        self.sinks = list(filter(lambda sink: app in get_app_name(sink), pulse.sink_input_list()))
        self.volume = self.get_volume()

    def __repr__(self):
        return f"Session(app={self.app}, index={self.idx})"

    def refresh_sinks(self):
        self.sinks = list(filter(lambda sink: self.app in get_app_name(sink), self.pulse.sink_input_list()))


class Master(Base):
    def __init__(self, idx: int, pulse: Pulse):
        self.app = 'master'
        super().__init__(idx=idx, pulse=pulse)
        self.sinks = pulse.sink_list()
        self.volume = self.get_volume()

    def __repr__(self):
        return f"Session(app={self.app}, index={self.idx}, volume={self.volume})"

    def refresh_sinks(self):
        self.sinks = self.pulse.sink_list()


class SessionGroup(Base):
    def __init__(self, idx: int, apps: List[str], pulse: Pulse, unmapped: bool = False):
        self.unmapped = unmapped
        self.apps = apps
        super().__init__(idx=idx, pulse=pulse)
        if self.unmapped:
            self.sinks = list(filter(lambda sink: all(app not in get_app_name(sink) for app in self.apps),
                                     pulse.sink_input_list()))
            # self.sinks = list(filter(lambda sink: get_app_name(sink) not in self.apps, pulse.sink_input_list()))
        else:
            self.sinks = list(filter(lambda sink: any(app in get_app_name(sink) for app in self.apps),
                                     pulse.sink_input_list()))
            # self.sinks = list(filter(lambda sink: get_app_name(sink) in self.apps, pulse.sink_input_list()))
        self.volume = self.get_volume()

    def __repr__(self):
        return f"SessionGroup(index={self.idx}, " f"apps={[app for app in self.apps]}), volume={self.volume}"

    def set_apps(self, apps: List[str]):
        self.apps = apps

    def refresh_sinks(self):
        if self.unmapped:
            self.sinks = list(filter(lambda sink: all(app not in get_app_name(sink) for app in self.apps),
                                     self.pulse.sink_input_list()))
        else:
            self.sinks = list(filter(lambda sink: any(app in get_app_name(sink) for app in self.apps),
                                     self.pulse.sink_input_list()))
