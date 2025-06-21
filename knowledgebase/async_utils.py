# knowledge_base/async_utils.py
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from functools import wraps


def run_async_in_thread(async_func):
    """
    Decorator to run async functions in a separate thread
    to avoid event loop conflicts in Django views
    """
    @wraps(async_func)
    def wrapper(*args, **kwargs):
        def run_in_thread():
            # Create new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(async_func(*args, **kwargs))
            finally:
                loop.close()
        
        # Run in a separate thread
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(run_in_thread)
            return future.result()
    
    return wrapper


def run_async_safely(async_func, *args, **kwargs):
    """
    Safely run async function from sync context
    """
    def run_in_thread():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(async_func(*args, **kwargs))
        finally:
            loop.close()
    
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(run_in_thread)
        return future.result()