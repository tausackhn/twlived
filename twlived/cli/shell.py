from ._common import COMMON_ARGS, Command


def _shell():
    pass


command = Command(
    name='shell',
    description='Start an Python IDLE (or ipython if it exists) with useful prepared objects',
    func=_shell,
    arguments=COMMON_ARGS,
)
