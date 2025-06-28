"""Boot configuration for the Taupunkt project."""
import gc
import micropython

micropython.opt_level(2)
gc.threshold(4096)
micropython.alloc_emergency_exception_buf(100)
print("Boot sequence complete")
