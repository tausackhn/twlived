from abc import ABC, abstractmethod
from itertools import chain
from typing import Type, Optional, Dict, List

from pydantic import BaseModel


# TODO: rewrite w/o pydantic and with read-only attributes
class BaseEvent(BaseModel):  # type: ignore
    pass


class Provider:
    def __init__(self) -> None:
        self.subscribers: Dict[Type[BaseEvent], List['Subscriber']] = {}

    def notify(self, event: BaseEvent) -> None:
        cls = event.__class__
        if BaseEvent in cls.__bases__ or type in cls.__bases__:
            raise TypeError('BaseEvent instances can not be used as event. Only subclass of BaseEvent can be used.')
        # TODO: remove ignore
        # noinspection PyTypeChecker
        for subscriber in chain(self.subscribers.get(cls.__bases__[0], []),  # type: ignore
                                self.subscribers.get(cls, [])):  # type: ignore
            subscriber.handle(event)

    def subscribe(self, event_type: Type[BaseEvent], subscriber: 'Subscriber') -> None:
        self.subscribers.setdefault(event_type, []).append(subscriber)

    def unsubscribe(self, event_type: Type[BaseEvent], subscriber: 'Subscriber') -> None:
        self.subscribers[event_type].remove(subscriber)

    def connect(self, *clients: 'ProviderClientMixin') -> None:
        for client in clients:
            client.connect_to(self)


class ProviderClientMixin:
    def __init__(self) -> None:
        self.provider: Optional[Provider] = None

    def connect_to(self, message_center: Provider) -> None:
        self.provider = message_center


class Publisher(ProviderClientMixin):
    def __init__(self) -> None:
        super().__init__()

    def publish(self, event: BaseEvent) -> None:
        if not self.provider:
            raise AttributeError('No provider specified.')
        self.provider.notify(event)


class Subscriber(ProviderClientMixin, ABC):
    def __init__(self) -> None:
        super().__init__()

    def subscribe(self, event_type: Type[BaseEvent]) -> None:
        if not self.provider:
            raise AttributeError('No provider specified.')
        self.provider.subscribe(event_type, self)

    def unsubscribe(self, event_type: Type[BaseEvent]) -> None:
        if not self.provider:
            raise AttributeError('No provider specified.')
        self.provider.unsubscribe(event_type, self)

    @abstractmethod
    def handle(self, event: BaseEvent) -> None:
        pass
