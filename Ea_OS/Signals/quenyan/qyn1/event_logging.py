from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional

from .string_table import StringTable


class EventPayloadClass(str, Enum):
    NONE = "NONE"
    ID = "ID"
    STR = "STR"
    NUM = "NUM"
    BOOL = "BOOL"
    OTHER = "OTHER"


@dataclass
class EncodingEvent:
    file_id: str
    position: int
    token_key: str
    payload_class: EventPayloadClass
    payload_value: Any = None
    payload_domain: Optional[str] = None
    string_index: Optional[int] = None
    string_hash: Optional[str] = None
    raw_string: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "file_id": self.file_id,
            "position": self.position,
            "token_key": self.token_key,
            "payload_class": self.payload_class.value,
            "payload_value": self.payload_value,
            "payload_domain": self.payload_domain,
            "string_index": self.string_index,
            "string_hash": self.string_hash,
        }

    @staticmethod
    def from_dict(data: Mapping[str, Any]) -> "EncodingEvent":
        payload_class = EventPayloadClass(data.get("payload_class", EventPayloadClass.NONE))
        return EncodingEvent(
            file_id=str(data.get("file_id", "")),
            position=int(data.get("position", 0)),
            token_key=str(data.get("token_key", "")),
            payload_class=payload_class,
            payload_value=data.get("payload_value"),
            payload_domain=data.get("payload_domain"),
            string_index=data.get("string_index"),
            string_hash=data.get("string_hash"),
        )

    def payload_key(self) -> tuple[str, str | None, str | None]:
        value_repr: str | None
        if self.payload_value is None:
            value_repr = None
        elif isinstance(self.payload_value, (str, int, float, bool)):
            value_repr = str(self.payload_value)
        else:
            value_repr = json.dumps(self.payload_value, sort_keys=True)
        return (self.payload_class.value, value_repr, self.payload_domain)


@dataclass
class EncodingEventLog:
    file_id: str
    token_keys: List[str] = field(default_factory=list)
    events: List[EncodingEvent] = field(default_factory=list)
    _payload_counts: Counter[int] = field(default_factory=Counter)

    def record_token(self, token_key: str) -> int:
        position = len(self.token_keys)
        self.token_keys.append(token_key)
        return position

    def record_payload(
        self,
        position: int,
        payload_class: EventPayloadClass,
        *,
        payload_value: Any = None,
        payload_domain: Optional[str] = None,
        raw_string: Optional[str] = None,
    ) -> None:
        self._payload_counts[position] += 1
        string_hash = None
        string_index = None
        if payload_class in {EventPayloadClass.ID, EventPayloadClass.STR} and raw_string is not None:
            string_hash = hashlib.sha256(raw_string.encode("utf-8")).hexdigest()
        event = EncodingEvent(
            file_id=self.file_id,
            position=position,
            token_key=self.token_keys[position],
            payload_class=payload_class,
            payload_value=payload_value,
            payload_domain=payload_domain,
            string_index=string_index,
            string_hash=string_hash,
            raw_string=raw_string,
        )
        self.events.append(event)

    def attach_string_table(self, table: StringTable) -> None:
        for event in self.events:
            if event.raw_string is None:
                continue
            try:
                index = table.index_for(event.raw_string)
            except KeyError:
                continue
            event.string_index = index
            event.payload_value = index if event.payload_value is None else event.payload_value

    def finalize(self) -> None:
        for position, token_key in enumerate(self.token_keys):
            if self._payload_counts[position]:
                continue
            self.events.append(
                EncodingEvent(
                    file_id=self.file_id,
                    position=position,
                    token_key=token_key,
                    payload_class=EventPayloadClass.NONE,
                )
            )
        self.events.sort(key=lambda event: event.position)

    def to_dict(self) -> Dict[str, Any]:
        return {"events": [event.as_dict() for event in self.events]}


__all__ = [
    "EncodingEvent",
    "EncodingEventLog",
    "EventPayloadClass",
]
