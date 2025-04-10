from sdbus import sd_bus_open_system, set_default_bus
from sdbus_async.networkmanager import (
    NetworkManager,
    NetworkConnectionSettings,
    ActiveConnection,
    NetworkDeviceGeneric,
)
from sdbus_async.networkmanager.enums import DeviceType, DeviceMetered

from loguru import logger

set_default_bus(sd_bus_open_system())
nm = NetworkManager()


async def get_device_types():
    device_types = {}
    devices_paths = await nm.get_devices()
    for device_path in devices_paths:
        generic_device = NetworkDeviceGeneric(device_path)
        device_type = await generic_device.device_type
        interface = await generic_device.interface

        device_types[interface] = device_type

    logger.debug(device_types)
    return device_types


async def get_current_network_connection() -> dict[str, dict[str, tuple[str, any]]]:
    connections_paths: list[str] = await nm.active_connections

    active_connections: list[ActiveConnection] = [
        ActiveConnection(x) for x in connections_paths
    ]

    for connection in active_connections:
        default = await connection.default

        if not default:
            continue

        conn = await connection.connection

        network = NetworkConnectionSettings(conn)
        network_settings = await network.get_settings()

        logger.debug(network_settings)
        return network_settings


async def check_network_conditions(
    wifi_only: bool, ssid: str | None, not_metered: bool
) -> bool:
    settings = await get_current_network_connection()
    if not settings:
        logger.warning("Not on a network connection")
        return False

    device_types = await get_device_types()
    connection = settings.get("connection")

    if not_metered:
        network_metered = connection.get("metered")
        if not network_metered:
            logger.warning("Failed to get network metering settings")
            return False

        if network_metered[1] == DeviceMetered.YES:
            logger.warning("Network is metered")
            return False

    if wifi_only:
        connection_device = connection.get("interface-name")
        if not connection_device:
            logger.warning("Failed to get network device")
            return False

        connection_device_type = device_types.get(connection_device[1])
        if not connection_device_type:
            logger.warning(f"Failed to get {connection_device[1]} device type")
            return False

        if connection_device_type != DeviceType.WIFI:
            logger.warning(
                f"{connection_device[1]} is type {connection_device_type} not WIFI"
            )
            return False

        if ssid:
            wireless_settings = settings.get("802-11-wireless")
            if not wireless_settings:
                logger.warning("Failed to get wireless settings")

            wireless_settings_ssid = wireless_settings.get("ssid")
            if not ssid:
                logger.warning("Failed to get SSID from wireless settings")

            wireless_settings_ssid_name = wireless_settings_ssid[1].decode("utf-8")
            if wireless_settings_ssid_name != ssid:
                logger.warning(
                    f"SSID {wireless_settings_ssid_name} does not match {ssid}"
                )
                return False

    return True
