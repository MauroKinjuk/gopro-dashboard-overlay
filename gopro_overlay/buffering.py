import ctypes
import io
import multiprocessing
import os
import queue
import threading
from io import BufferedWriter
from multiprocessing.shared_memory import SharedMemory
from typing import Callable, Any, Optional, Tuple

from PIL import Image, ImageDraw

from gopro_overlay.dimensions import Dimension
from gopro_overlay.widgets.widgets import SimpleFrameSupplier


class DrawBuffer:
    def draw(self, f: Callable[[Image.Image], Any]):
        raise NotImplementedError()


class ThreadedWriter:
    """Pushes frame writes onto a background thread so the draw loop doesn't
    block waiting for ffmpeg to drain the pipe. os.write releases the GIL,
    so this overlaps pipe I/O with drawing. Bounded queue keeps backpressure
    and limits memory use."""

    def __init__(self, writer: BufferedWriter, depth: int = 2):
        self.writer = writer
        self.error: Optional[Exception] = None
        self.queue: queue.Queue = queue.Queue(maxsize=depth)
        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()

    def _worker(self):
        while True:
            item = self.queue.get()
            if item is None:
                return
            try:
                self.writer.write(item)
                self.writer.flush()
            except Exception as e:
                self.error = e
                return

    def write(self, data):
        while self.error is None:
            try:
                self.queue.put(data, timeout=0.5)
                return
            except queue.Full:
                pass
        raise self.error

    def close(self):
        self.queue.put(None)
        self.thread.join()
        if self.error is not None:
            raise self.error


class SingleBuffer(DrawBuffer):
    def __init__(self, size: Dimension, background: Tuple, writer: BufferedWriter):
        self.supplier = SimpleFrameSupplier(size, background)
        self.writer = writer

    def draw(self, f: Callable[[Image.Image], Any]):
        image = self.supplier.drawing_frame()
        f(image)
        self.writer.write(image.tobytes())

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if isinstance(self.writer, ThreadedWriter):
            self.writer.close()


class SerialisedWriter(io.BufferedWriter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.lock = multiprocessing.Lock()

    def write(self, __buffer) -> int:
        with self.lock:
            try:
                return super().write(__buffer)
            finally:
                super().flush()


cond_timeout = 1.0


def raw_image(dimensions: Dimension, buffer) -> Image.Image:
    image = Image.frombuffer("RGBA", (dimensions.x, dimensions.y), buffer, "raw", "RGBA", 0, 1)
    image.readonly = 0
    return image


class Frame:
    def __init__(self, shm: SharedMemory, quit: multiprocessing.Value, size: Dimension, background: Tuple, count: int):
        self.shm = shm
        self.size = size
        self.count = count
        self.quit = quit
        self.background = background
        self.buffer_size = (size.x * size.y * 4)

        self.memory = shm.buf[self.buffer_size * self.count:self.buffer_size * (self.count + 1)]

        self.image = raw_image(size, self.memory)
        self.im_draw = ImageDraw.ImageDraw(self.image)

        self.active = multiprocessing.Lock()
        self.can_draw = multiprocessing.Condition(self.active)
        self.can_write = multiprocessing.Condition(self.active)

        self.ctypes_buffer = ctypes.c_char.from_buffer(self.memory)

        self.drawn_frame_number = multiprocessing.Value(ctypes.c_long)
        self.drawn_frame_number.value = -1

        self.written_frame_number = multiprocessing.Value(ctypes.c_long)
        self.written_frame_number.value = -1

        self.clear()

    def wake(self):
        with self.can_draw:
            self.can_draw.notify()
        with self.can_write:
            self.can_write.notify()

    def clear(self):
        ctypes.memset(ctypes.byref(self.ctypes_buffer), 0x00, self.buffer_size)
        if self.background != (0, 0, 0, 0):
            self.im_draw.rectangle((0, 0, self.size.x, self.size.y), self.background)

    def draw(self, f: Callable[[Image.Image], None]) -> bool:
        with self.can_draw:
            while not self.can_draw.wait_for(
                    predicate=lambda: self.quit.value == 1 or self.written_frame_number.value == self.drawn_frame_number.value,
                    timeout=cond_timeout):
                pass

        if self.drawn_frame_number.value == self.written_frame_number.value:
            f(self.image)

        self.drawn_frame_number.value += 1
        with self.can_write:
            self.can_write.notify()

        if self.quit.value == 1:
            return False
        return True

    def copy(self) -> Image.Image:
        """Return a copy of this image, not from shared memory"""
        c = Image.new("RGBA", self.size.tuple())
        c.paste(self.image)
        return c

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.wake()
        del self.ctypes_buffer
        self.image.close()
        self.memory = None

    def write(self, writer: io.BytesIO) -> bool:
        with self.can_write:
            while not self.can_write.wait_for(
                    predicate=lambda: self.quit.value == 1 or self.drawn_frame_number.value > self.written_frame_number.value,
                    timeout=cond_timeout):
                pass

        if self.drawn_frame_number.value > self.written_frame_number.value:
            writer.write(self.memory)
            self.clear()
            self.written_frame_number.value += 1

            with self.can_draw:
                self.can_draw.notify()

        if self.quit.value == 1:
            return False
        return True


def p_writer(frame: Frame, writer: io.BytesIO):
    try:
        while True:
            if not frame.write(writer):
                break
    except KeyboardInterrupt:
        pass


class DoubleBuffer(DrawBuffer):
    def __init__(self, size: Dimension, background: Tuple, writer: BufferedWriter):
        shm_name = f"gopro.{os.getpid()}"
        buffer_size = (size.x * size.y * 4)
        shm_size = buffer_size * 2
        self.shm = SharedMemory(create=True, name=shm_name, size=shm_size)
        self.quit = multiprocessing.Value(ctypes.c_int)

        self.frame0 = Frame(self.shm, self.quit, size, background, 0)
        self.frame1 = Frame(self.shm, self.quit, size, background, 1)

        writer = SerialisedWriter(writer)

        self.worker1 = multiprocessing.Process(target=p_writer, args=(self.frame0, writer))
        self.worker1.start()
        self.worker2 = multiprocessing.Process(target=p_writer, args=(self.frame1, writer))
        self.worker2.start()

        self.counter = 0

    def draw(self, f: Callable[[Image.Image], Any]):
        current_frame = self.frame0 if self.counter % 2 == 0 else self.frame1
        current_frame.draw(lambda image: f(image))
        self.counter += 1

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.quit.value = 1

        self.frame0.__exit__(*args)
        self.frame1.__exit__(*args)

        self.worker1.join(timeout=1.0)
        self.worker2.join(timeout=1.0)

        del self.frame0
        del self.frame1

        self.shm.unlink()
