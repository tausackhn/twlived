# encoding=utf-8
class View(object):
    def __init__(self):
        self._count = 0
        self._size = 0

    def __call__(self, **kwargs):
        self._count += 1
        self._size += int(kwargs['size'])
        print(f'\r Downloaded {self._count} segments. Total size {self._size}')
