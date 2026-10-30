"""Binary sensor platform — HACS-style transmitter/cover/battery presentation."""

from typing import Any, override

from easywave_home_control.codec import ButtonPushEvent

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import STATE_OFF, STATE_ON, EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import EasywaveConfigEntry
from .const import (
    CONF_BUTTON_COUNT,
    CONF_ENTRY_TYPE,
    CONF_SENSOR_CAPABILITIES,
    ENTRY_TYPE_NEO_SENSOR,
    ENTRY_TYPE_TRANSMITTER,
    EVENT_TYPE_CLOSED,
    EVENT_TYPE_OPENED,
    EasywaveTransmitterFeature,
)
from .devices import get_devices
from .entity import EasywaveDeviceEntry, EasywaveNeoSensorEntity, EasywaveTransmitterEntity
from .transmitter_entities import async_setup_transmitter_entities


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EasywaveConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Easywave binary sensors."""
    for device in get_devices(entry):
        entry_type = device.data.get(CONF_ENTRY_TYPE)
        if entry_type == ENTRY_TYPE_TRANSMITTER:
            await async_setup_transmitter_entities(
                hass, entry, device, async_add_entities, "binary_sensor"
            )
        elif entry_type == ENTRY_TYPE_NEO_SENSOR:
            capabilities = int(device.data.get(CONF_SENSOR_CAPABILITIES, 0))
            if capabilities & 1:
                async_add_entities(
                    [EasywaveNeoBatteryBinarySensor(entry, device)],
                    config_subentry_id=device.subentry_id,
                )


class EasywaveTransmitterCoverStateBinarySensor(
    EasywaveTransmitterEntity, RestoreEntity, BinarySensorEntity
):
    """Open/Closed cover state for op-2 cover transmitters (HACS UX)."""

    _attr_device_class = BinarySensorDeviceClass.OPENING

    def __init__(
        self,
        entry: EasywaveConfigEntry,
        device: EasywaveDeviceEntry,
        *,
        pair: str,
    ) -> None:
        """Initialize for button pair ab or cd."""
        self._pair = pair
        button_count = int(device.data.get(CONF_BUTTON_COUNT, 2))
        if pair == "cd":
            suffix = "state_cd"
            self._attr_translation_key = "state_cd"
            self._open_button = 2  # C
            self._close_button = 3  # D
        elif button_count >= 4:
            suffix = "state_ab"
            self._attr_translation_key = "state_ab"
            self._open_button = 0  # A
            self._close_button = 1  # B
        else:
            # Single cover pair → HACS name "State" / "Zustand"
            suffix = "state"
            self._attr_translation_key = "transmitter_state_cover"
            self._open_button = 0  # A
            self._close_button = 1  # B
        super().__init__(entry, device, suffix)
        self._attr_is_on = False  # on = open
        self._attr_supported_features = int(
            EasywaveTransmitterFeature.COVER_OPEN
            | EasywaveTransmitterFeature.COVER_CLOSE
        )

    @override
    async def async_added_to_hass(self) -> None:
        """Restore cover open/closed."""
        if (last := await self.async_get_last_state()) is not None:
            self._attr_is_on = last.state == "on"
        await super().async_added_to_hass()

    @override
    @property
    def icon(self) -> str:
        """Return shutter icon matching open/closed (HACS UX)."""
        if self._attr_is_on:
            return "mdi:window-shutter-open"
        return "mdi:window-shutter"

    @override
    def handle_telegram(self, event: Any) -> None:
        """Map A/C → open, B/D → closed."""
        if not isinstance(event, ButtonPushEvent):
            return
        if event.button == self._open_button:
            self._attr_is_on = True
            self.async_write_ha_state()
            self._coordinator.fire_device_event(
                self._device_id, EVENT_TYPE_OPENED, subtype="up"
            )
        elif event.button == self._close_button:
            self._attr_is_on = False
            self.async_write_ha_state()
            self._coordinator.fire_device_event(
                self._device_id, EVENT_TYPE_CLOSED, subtype="down"
            )


class EasywaveTransmitterBatteryBinarySensor(
    EasywaveTransmitterEntity, RestoreEntity, BinarySensorEntity
):
    """Transmitter battery as a standard battery binary sensor (on = low).

    Additional to the CORE-aligned enum sensor (unique_id ..._battery_warning),
    which Home Assistant does not recognise as a battery entity and therefore
    never lists in battery overviews. Same LOWBAT handling; the battery device
    events are still fired by the enum sensor only.
    """

    _attr_device_class = BinarySensorDeviceClass.BATTERY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    # Same value as EasywaveTransmitterBatterySensor._CLEAR_THRESHOLD.
    _CLEAR_THRESHOLD = 2

    def __init__(
        self, entry: EasywaveConfigEntry, device: EasywaveDeviceEntry
    ) -> None:
        """Initialize; state is unknown until the first LOWBAT report."""
        super().__init__(entry, device, "battery")
        self._attr_is_on: bool | None = None
        self._ok_streak = 0

    @override
    async def async_added_to_hass(self) -> None:
        """Restore the last known battery state before subscribing."""
        if (last := await self.async_get_last_state()) is not None and (
            last.state in (STATE_ON, STATE_OFF)
        ):
            self._attr_is_on = last.state == STATE_ON
        await super().async_added_to_hass()

    @callback
    def handle_telegram(self, event: Any) -> None:
        """Battery state is updated via handle_battery_status."""

    @override
    @callback
    def handle_battery_status(self, is_low: bool) -> None:
        """Update from the LOWBAT flag of a PUSH telegram."""
        if is_low:
            self._ok_streak = 0
            if self._attr_is_on is not True:
                self._attr_is_on = True
                self.async_write_ha_state()
            return
        if self._attr_is_on is False:
            return
        self._ok_streak += 1
        if self._ok_streak >= self._CLEAR_THRESHOLD:
            self._attr_is_on = False
            self._ok_streak = 0
            self.async_write_ha_state()


class EasywaveNeoBatteryBinarySensor(EasywaveNeoSensorEntity, BinarySensorEntity):
    """Neo sensor battery warning."""

    _attr_device_class = BinarySensorDeviceClass.BATTERY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "battery_warning"

    def __init__(
        self, entry: EasywaveConfigEntry, device: EasywaveDeviceEntry
    ) -> None:
        """Initialize."""
        super().__init__(entry, device, "battery")
        self._attr_is_on = False

    @override
    def handle_telegram(self, event: Any) -> None:
        """Keep last known battery state."""
