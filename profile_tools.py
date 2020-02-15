import inspect
import logging
import time

cumulative_data = {}
method_names = {}

def profile(f):
    def f_timer(*args, **kwargs):
        start = time.time()
        result = f(*args, **kwargs)
        end = time.time()
        logging.info("{}.{} call took {}s.".format(f.__module__, f.__name__, end-start))

        return result

    return f_timer

def profile_cumulative(f):
    def f_timer(*args, **kwargs):
        start = time.time()
        result = f(*args, **kwargs)
        end = time.time()

        if f.__name__ not in cumulative_data:
	        try:
	        	is_method = inspect.getfullargspec(f)[0][0] == 'self'
	        except IndexError:
	        	is_method = False

	        name = ""

	        if is_method:
	        	name = "{}.{}".format(args[0].__class__.__name__, f.__name__)
	        else:
	        	name = f.__name__

        	cumulative_data[f.__name__] = 0
        	method_names[f.__name__] = name

        cumulative_data[f.__name__] += end-start

        return result

    return f_timer

def log_digest():
    for entry in cumulative_data.items():
        logging.info("Total time spent on '{}': {:.3f}s".format(method_names[entry[0]], entry[1]))