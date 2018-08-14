from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Type, Union

EventHandlerT = Callable[['BaseEvent'], None]


class BaseEventMeta(type):
    def __new__(mcs, name, bases, dct, max_inheritance_level: int = 0):
        cls = dataclass(super().__new__(mcs, name, bases, dct), frozen=True)  # type: ignore
        cls.__max_inheritance_level__ = max_inheritance_level
        cls.__inheritance_level__ = 0
        for base in bases:
            if hasattr(base, '__inheritance_level__') and cls.__inheritance_level__ <= base.__inheritance_level__:
                cls.__max_inheritance_level__ = base.__max_inheritance_level__
                cls.__inheritance_level__ = base.__inheritance_level__ + 1
        if cls.__inheritance_level__ > cls.__max_inheritance_level__:
            raise ValueError(
                f'{cls.__name__} can not be created. Inheritance level {cls.__max_inheritance_level__} exceeded')
        return cls


class BaseEvent(metaclass=BaseEventMeta, max_inheritance_level=1):
    pass


class Provider:
    def __init__(self) -> None:
        self.subscribers: Dict[Type[BaseEvent], List['Subscriber']] = defaultdict(list)

    def notify(self, event: BaseEvent) -> None:
        event_cls = type(event)
        if event_cls == BaseEvent:
            raise TypeError('BaseEvent instance can not be used as event. Supports only subclass instances.')

        for subscriber in self.subscribers.get(event_cls, []):
            subscriber.handle(event)

    def subscribe(self, event_type: Union[Type[BaseEvent], List[Type[BaseEvent]]], subscriber: 'Subscriber') -> None:
        if isinstance(event_type, list):
            for event_type_ in event_type:
                self.subscribers[event_type_].append(subscriber)
        else:
            self.subscribers[event_type].append(subscriber)

    def unsubscribe(self, event_type: Union[Type[BaseEvent], List[Type[BaseEvent]]], subscriber: 'Subscriber') -> None:
        if isinstance(event_type, list):
            for event_type_ in event_type:
                self.subscribers[event_type_].remove(subscriber)
        else:
            self.subscribers[event_type].remove(subscriber)

    def connect(self, *clients: Union['ProviderClientMixin', EventHandlerT]) -> None:
        for client in clients:
            if isinstance(client, ProviderClientMixin):
                client.connect_to(self)
            elif callable(client) and hasattr(client, '_subscriber'):
                getattr(client, '_subscriber').connect_to(self)
            else:
                raise TypeError(f'{client} do not have connect_to method')


class ProviderClientMixin:
    def __init__(self) -> None:
        self.provider: Optional[Provider] = None

    def connect_to(self, message_center: Provider) -> None:
        self.provider = message_center


class Publisher(ProviderClientMixin):
    def __init__(self) -> None:
        super().__init__()

    def publish(self, event: BaseEvent) -> None:
        if self.provider:
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


def handle(event_type: Type[BaseEvent], *,
           message_center: Optional[Provider] = None) -> Callable[[EventHandlerT], EventHandlerT]:
    def decorator(func: EventHandlerT) -> EventHandlerT:
        if not hasattr(func, '_subscriber'):
            class _Subscriber(Subscriber):
                def handle(self, event: BaseEvent) -> None:
                    func(event)

            setattr(func, '_subscriber', _Subscriber())
        if message_center:
            getattr(func, '_subscriber').connect_to(message_center)
        getattr(func, '_subscriber').subscribe(event_type)
        return func

    return decorator
