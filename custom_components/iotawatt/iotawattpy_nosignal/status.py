"""Live readings and device status reported by the IoTaWatt ``/status`` endpoint.

Modified as part of the iotawattpy-nosignal fork
(https://github.com/No-Signal/iotawattpy), see README.md.

The response shapes follow ``handleStatus()`` in the firmware's
``Firmware/IotaWatt/webServer.cpp`` (https://github.com/boblemaire/IoTaWatt).
Fields can be missing on older firmware; they are parsed as ``None``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import math
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable


def _toFloat(value: Any) -> float | None:
    """Convert a JSON number or numeric string to a finite float, else ``None``."""
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _toInt(value: Any) -> int | None:
    """Convert a JSON number or numeric string to int, else ``None``."""
    result = _toFloat(value)
    return None if result is None else int(result)


def _toStr(value: Any) -> str | None:
    """Convert a JSON value to str, keeping ``None``."""
    return None if value is None else str(value)


def _toBool(value: Any) -> bool | None:
    """Convert a JSON boolean (or 0/1) to bool, else ``None``."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    return None


def _toTime(value: Any) -> datetime | None:
    """Convert UNIX seconds (UTC) to an aware datetime; 0 means unset."""
    seconds = _toFloat(value)
    if not seconds:
        return None
    try:
        return datetime.fromtimestamp(seconds, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


@dataclass(frozen=True)
class LiveReading:
    """A live (about 1 second average) reading of one input or output.

    The firmware's ``statService`` refreshes these values every second. Input
    channels set ``watts`` and ``power_factor`` (power channels) or ``volts``
    and ``hz`` (voltage channels). Outputs set ``value`` and ``unit``, the
    output script evaluated against the same live values.
    """

    watts: float | None = None
    power_factor: float | None = None
    volts: float | None = None
    hz: float | None = None
    value: float | None = None
    unit: str | None = None

    @classmethod
    def fromInput(cls, data: dict[str, Any]) -> LiveReading:
        """Parse an entry of the ``inputs`` array.

        ``Watts`` is sent as a string (``String(value, 0)``) and is zeroed by
        the firmware when its magnitude is below 2 W.
        """
        return cls(
            watts=_toFloat(data.get("Watts")),
            power_factor=_toFloat(data.get("Pf")),
            volts=_toFloat(data.get("Vrms")),
            hz=_toFloat(data.get("Hz")),
        )

    @classmethod
    def fromOutput(cls, data: dict[str, Any]) -> LiveReading:
        """Parse an entry of the ``outputs`` array."""
        return cls(value=_toFloat(data.get("value")), unit=_toStr(data.get("units")))


def parseLiveStatus(data: dict[str, Any]) -> dict[str, LiveReading]:
    """Parse a ``/status?inputs&outputs`` response into live readings.

    Keys match ``Iotawatt.getSensors()`` keys: ``input_{channel}`` and
    ``output_{name}``.
    """
    readings: dict[str, LiveReading] = {}
    for entry in data.get("inputs") or []:
        if entry.get("channel") is not None:
            readings[f"input_{entry['channel']}"] = LiveReading.fromInput(entry)
    for entry in data.get("outputs") or []:
        if entry.get("name") is not None:
            readings[f"output_{entry['name']}"] = LiveReading.fromOutput(entry)
    return readings


def _parseEntries[T](
    entries: Any, parse: Callable[[dict[str, Any]], T]
) -> tuple[T, ...] | None:
    """Parse an array of objects with an ``id``, skipping entries without one."""
    if not isinstance(entries, list):
        return None
    return tuple(
        parse(entry)
        for entry in entries
        if isinstance(entry, dict) and entry.get("id") is not None
    )


@dataclass(frozen=True)
class DeviceSettings:
    """The ``device`` section: device configuration."""

    name: str | None
    timediff: int | None
    """Local time offset from UTC, in minutes."""
    allowdst: bool | None
    """Whether a daylight saving time rule is configured."""
    update: str | None
    """Firmware auto-update class (e.g. ``MAJOR``, ``MINOR``, ``NONE``)."""

    @classmethod
    def fromJson(cls, data: dict[str, Any]) -> DeviceSettings:
        """Parse the ``device`` section."""
        return cls(
            name=_toStr(data.get("name")),
            timediff=_toInt(data.get("timediff")),
            allowdst=_toBool(data.get("allowdst")),
            update=_toStr(data.get("update")),
        )


@dataclass(frozen=True)
class DeviceStats:
    """The ``stats`` section: sampling, uptime and firmware statistics."""

    cyclerate: float | None
    """Samples per AC cycle."""
    chanrate: float | None
    """AC cycles sampled per second."""
    starttime: datetime | None
    """When the firmware last started."""
    currenttime: datetime | None
    """The device clock."""
    runseconds: int | None
    """Seconds since the firmware started."""
    stack: int | None
    """Free heap, in bytes."""
    version: str | None
    """Firmware version as reported, e.g. ``02_08_04``."""
    frequency: float | None
    """AC line frequency, in Hz."""
    lowbat: bool | None
    """Whether the real-time clock battery is low."""

    @classmethod
    def fromJson(cls, data: dict[str, Any]) -> DeviceStats:
        """Parse the ``stats`` section."""
        return cls(
            cyclerate=_toFloat(data.get("cyclerate")),
            chanrate=_toFloat(data.get("chanrate")),
            starttime=_toTime(data.get("starttime")),
            currenttime=_toTime(data.get("currenttime")),
            runseconds=_toInt(data.get("runseconds")),
            stack=_toInt(data.get("stack")),
            version=_toStr(data.get("version")),
            frequency=_toFloat(data.get("frequency")),
            lowbat=_toBool(data.get("lowbat")),
        )


@dataclass(frozen=True)
class WifiStatus:
    """The ``wifi`` section.

    Only ``connecttime`` is sent while the device is disconnected.
    """

    connecttime: datetime | None
    """When the current WiFi connection was made; ``None`` if disconnected."""
    ssid: str | None
    ip: str | None
    channel: int | None
    rssi: int | None
    """Signal strength, in dBm."""
    mac: str | None
    """MAC address as reported, e.g. ``A0:20:A6:00:00:01``."""

    @classmethod
    def fromJson(cls, data: dict[str, Any]) -> WifiStatus:
        """Parse the ``wifi`` section."""
        return cls(
            connecttime=_toTime(data.get("connecttime")),
            ssid=_toStr(data.get("SSID")),
            ip=_toStr(data.get("IP")),
            channel=_toInt(data.get("channel")),
            rssi=_toInt(data.get("RSSI")),
            mac=_toStr(data.get("mac")),
        )


@dataclass(frozen=True)
class DatalogStatus:
    """An entry of the ``datalogs`` array.

    ``id`` is ``Current``, ``History`` or the name of an integrator.
    """

    id: str
    firstkey: datetime | None
    """Time of the oldest record."""
    lastkey: datetime | None
    """Time of the newest record."""
    size: int | None
    """File size, in bytes."""
    interval: int | None
    """Record interval, in seconds."""

    @classmethod
    def fromJson(cls, data: dict[str, Any]) -> DatalogStatus:
        """Parse an entry of the ``datalogs`` array."""
        return cls(
            id=str(data["id"]),
            firstkey=_toTime(data.get("firstkey")),
            lastkey=_toTime(data.get("lastkey")),
            size=_toInt(data.get("size")),
            interval=_toInt(data.get("interval")),
        )


@dataclass(frozen=True)
class UploaderStatus:
    """An entry of the ``uploaders`` array."""

    id: str
    """Uploader name, e.g. ``influxDB``, ``Emoncms`` or ``PVoutput``."""
    status: str | None
    """``running`` or ``stopped``."""
    lastpost: datetime | None
    """Time of the last data uploaded."""
    message: str | None
    """Last status or error message, if any."""

    @classmethod
    def fromJson(cls, data: dict[str, Any]) -> UploaderStatus:
        """Parse an entry of the ``uploaders`` array."""
        return cls(
            id=str(data["id"]),
            status=_toStr(data.get("status")),
            lastpost=_toTime(data.get("lastpost")),
            message=_toStr(data.get("message")),
        )


@dataclass(frozen=True)
class DeviceStatus:
    """Device health information, as shown on the device's Status page.

    A section is ``None`` when the firmware did not send it.
    """

    device: DeviceSettings | None
    stats: DeviceStats | None
    wifi: WifiStatus | None
    datalogs: tuple[DatalogStatus, ...] | None
    uploaders: tuple[UploaderStatus, ...] | None

    @classmethod
    def fromJson(cls, data: dict[str, Any]) -> DeviceStatus:
        """Parse a ``/status?device&stats&wifi&datalogs&uploaders`` response."""
        device = data.get("device")
        stats = data.get("stats")
        wifi = data.get("wifi")
        return cls(
            device=(
                DeviceSettings.fromJson(device) if isinstance(device, dict) else None
            ),
            stats=DeviceStats.fromJson(stats) if isinstance(stats, dict) else None,
            wifi=WifiStatus.fromJson(wifi) if isinstance(wifi, dict) else None,
            datalogs=_parseEntries(data.get("datalogs"), DatalogStatus.fromJson),
            uploaders=_parseEntries(data.get("uploaders"), UploaderStatus.fromJson),
        )

    def getDatalog(self, log_id: str) -> DatalogStatus | None:
        """Return the datalog with the given id (e.g. ``Current``), if any."""
        return next((log for log in self.datalogs or () if log.id == log_id), None)
