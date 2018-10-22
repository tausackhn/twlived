import asyncio
import logging
import time
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from functools import partial
from itertools import takewhile
from typing import Awaitable, Callable, Dict, List, Optional, Type, Union

EventHandlerT = Callable[['BaseEvent'], Awaitable[None]]


@dataclass
class BaseEvent:
    created_at: float = field(init=False, compare=False)

    def __post_init__(self) -> None:
        self.created_at = time.time()


class Provider:
    def __init__(self) -> None:
        self.subscribers: Dict[Type[BaseEvent], List['Subscriber']] = defaultdict(list)

    async def notify(self, event: BaseEvent) -> None:
        def callback(subscriber_: Subscriber, t: asyncio.Task) -> None:
            # noinspection PyBroadException
            try:
                t.result()
            except Exception:
                logging.warning('Got exception when notifying {subscriber} with {event}:',
                                exc_info=True,
                                extra={'subscriber': subscriber_, 'event': event})

        event_superclasses = takewhile(lambda event_type: event_type is not object, type(event).mro())
        for subscribers in (self.subscribers.get(event_cls, []) for event_cls in event_superclasses):
            for subscriber in subscribers:
                task = asyncio.create_task(subscriber.handle(event))
                callback_ = partial(callback, subscriber)
                task.add_done_callback(callback_)

    def subscribe(self, subscriber: 'Subscriber', *event_types: Type[BaseEvent]) -> None:
        for event_type in event_types:
            self.subscribers[event_type].append(subscriber)

    def unsubscribe(self, subscriber: 'Subscriber', *event_types: Type[BaseEvent]) -> None:
        for event_type in event_types:
            self.subscribers[event_type].remove(subscriber)

    def connect(self, *clients: Union['ProviderClientMixin', EventHandlerT]) -> None:
        for client in clients:
            if isinstance(client, ProviderClientMixin):
                client.connect_to(self)
            elif callable(client) and hasattr(client, '_subscriber'):
                getattr(client, '_subscriber').connect_to(self)
            else:
                raise TypeError(f'{client} does not have connect_to method')


class ProviderClientMixin:
    def __init__(self) -> None:
        super().__init__()
        self.provider: Optional[Provider] = None

    def connect_to(self, message_center: Provider) -> None:
        self.provider = message_center


class Publisher(ProviderClientMixin):
    async def publish(self, event: BaseEvent) -> None:
        if self.provider:
            await self.provider.notify(event)


class Subscriber(ProviderClientMixin, ABC):
    def subscribe(self, *event_types: Type[BaseEvent]) -> None:
        if not self.provider:
            raise AttributeError('No provider specified.')
        self.provider.subscribe(self, *event_types)

    def unsubscribe(self, *event_types: Type[BaseEvent]) -> None:
        if not self.provider:
            raise AttributeError('No provider specified.')
        self.provider.unsubscribe(self, *event_types)

    @abstractmethod
    async def handle(self, event: BaseEvent) -> None:
        pass


def handle(*event_types: Type[BaseEvent],
           provider: Optional[Provider] = None) -> Callable[[EventHandlerT], EventHandlerT]:
    def decorator(func: EventHandlerT) -> EventHandlerT:
        if not hasattr(func, '_subscriber'):
            class _Subscriber(Subscriber):
                async def handle(self, event: BaseEvent) -> None:
                    await func(event)

            setattr(func, '_subscriber', _Subscriber())
        if provider:
            getattr(func, '_subscriber').connect_to(provider)
        getattr(func, '_subscriber').subscribe(*event_types)
        return func

    return decorator
