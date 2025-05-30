import os
import re
import sys
import logging
import requests
import functools

from typing import Union, List, Type, Optional
from logging import Logger, FileHandler, StreamHandler, Handler


DEFAULT_USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'


def parse_domain(domain: str):
    """Returns the root domain of the provided domain

    **Example**::

       >>> parse_domain('https://www.mymagento.com#new-products')
       'mymagento.com'

       >>> parse_domain('https://username:password@my-magento.mymagento.com:443/store')
       'my-magento.mymagento.com'

       >>> parse_domain('127.0.0.1/path/to/magento/')
       '127.0.0.1/path/to/magento'
    """
    match = re.match(
        pattern=r"^(?:https?://)?(?:[^@\n]+@)?(?:www\.)?([^:\n?#]+)",
        string=domain
    )
    if match:
        return match.group(1).rstrip('/')
    raise ValueError("Invalid format provided for ``domain``")


@functools.lru_cache
def get_agents() -> list:
    """Scrapes a list of user agents. Returns a default list if the scrape fails."""
    try:
        response = requests.get('https://www.whatismybrowser.com/guides/the-latest-user-agent/chrome')
        if response.ok:
            section = response.text.split('<h2>Latest Chrome on Windows 10 User Agents</h2>')[1]
            return [agent.split('<')[0] for agent in section.split('code\">')[1:]]
        else:
            raise RuntimeError("Unable to retrieve user agents")

    except Exception:
        return [DEFAULT_USER_AGENT]


def get_agent(index=0) -> str:
    """Returns a single user agent string from the specified index of the AGENTS list"""
    return get_agents()[index]  # Specify index only if you hardcode more than 1

def snake_to_camel(snake_str: str) -> str:
    components = snake_str.split('_')
    return components[0] + ''.join(x.title() for x in components[1:])

def get_payload_prefix(endpoint: str, payload_prefix: Optional[str] = None) ->str:

    if payload_prefix:
        return payload_prefix

    # if the payload_prefix was not given we contract it by using the last part after '/' and removing the finals s
    # so products become product
    # products/attributes/{attribute.attribute_code}/options -> option
    # if it's a special one we can override it be specifying it
    # Split the endpoint by '/' and get the last part
    last_segment = endpoint.split('/')[-1]
    # Strip the trailing 's' if present
    payload_prefix = last_segment.rstrip('s').replace('-', '_')

    return snake_to_camel(payload_prefix)


def mime_type(filename):
    extension = filename.split('.')[-1].lower()

    if extension in ['jpg', 'jpeg']:
        mime = 'image/jpeg'
    elif extension in ['png']:
        mime = 'image/png'
    elif extension in ['gif']:
        mime = 'image/gif'
    else:
        raise Exception('Unkown mime-type for extionsion {0} in {1}'.format(extension, filename))

    return mime

class LoggerUtils:
    """Utility class that simplifies access to logger handler info"""

    @staticmethod
    def get_handler_names(logger) -> List[str]:
        """Get all handler names"""
        return [handler.name for handler in logger.handlers]

    @staticmethod
    def get_stream_handlers(logger: Logger) -> List[Handler]:
        """Get all the StreamHandlers of the current logger (NOTE: StreamHandler subclasses excluded)"""
        return [handler for handler in logger.handlers if type(handler) == StreamHandler]

    @staticmethod
    def get_file_handlers(logger: Logger) -> List[FileHandler]:
        """Get all the FileHandlers of the current logger"""
        return [handler for handler in logger.handlers if isinstance(handler, FileHandler)]

    @staticmethod
    def get_log_files(logger: Logger) -> List[str]:
        """Get the log file paths from all FileHandlers of a logger"""
        return [handler.baseFilename for handler in LoggerUtils.get_file_handlers(logger)]

    @staticmethod
    def get_handler_by_log_file(logger: Logger, log_file: str) -> Union[FileHandler, List[FileHandler]]:
        """Returns the FileHandler logging to the specified file, given it exists"""
        handlers = [
            handler for handler in LoggerUtils.get_file_handlers(logger)
            if os.path.basename(handler.baseFilename) == log_file
        ]
        if handlers:
            if len(handlers) == 1:
                return handlers[0]
            return handlers

    @staticmethod
    def clear_handlers(logger: Logger) -> bool:
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
        return logger.handlers == []

    @staticmethod
    def clear_stream_handlers(logger: Logger) -> bool:
        """Removes all StreamHandlers from a logger"""
        for handler in LoggerUtils.get_stream_handlers(logger):
            logger.removeHandler(handler)
        return LoggerUtils.get_stream_handlers(logger) == []

    @staticmethod
    def clear_file_handlers(logger: Logger) -> bool:
        """Removes all FileHandlers from a logger"""
        for handler in LoggerUtils.get_file_handlers(logger):
            logger.removeHandler(handler)
        return LoggerUtils.get_file_handlers(logger) == []

    @staticmethod
    def map_handlers_by_name(logger: Logger):
        """Map the handlers of a logger first by type, and then by their name

        FileHandlers are mapped to both their handlers and log file, while StreamHandlers are just mapped to the handler
        Handlers without a name will be skipped, because look at the method name (:
        """
        mapping = {
            'stream': {},
            'file': {}
        }
        for stream_handler in LoggerUtils.get_stream_handlers(logger):
            if stream_handler.name:
                mapping['stream'][stream_handler.name] = stream_handler

        for file_handler in LoggerUtils.get_file_handlers(logger):
            if file_handler.name:
                entry = mapping['file'].setdefault(file_handler.name, {})
                entry['handler'] = file_handler
                entry['file'] = file_handler.baseFilename

        return mapping


class MagentoLogger:
    """Logging class used within the package

    :cvar PREFIX:           hardcoded prefix to use in log messages
    :cvar PACKAGE_LOG_NAME: the default name for the package logger
    :cvar CLIENT_LOG_NAME:  the default format for the client logger name
    :cvar LOG_MESSAGE:      the default format for the message component of log messages.
                            (Use magento.logger.LOG_MESSAGE for easy access)
    :cvar FORMATTER:        the default logging format
    :type FORMATTER:        logging.Formatter
    :cvar HANDLER_NAME:      the default format for the names of handlers created by this package
    """

    PREFIX = "MyMagento"
    PACKAGE_LOG_NAME = "my-magento"
    CLIENT_LOG_NAME = "{domain}_{username}"
    HANDLER_NAME = '{}__{}__{}'.format(PREFIX, '{name}', '{stdout_level}')

    LOG_MESSAGE = "|[ {pfx} | {name} ]|:  {message}".format(
        pfx=PREFIX, name="{name}", message="{message}"
    )

    FORMATTER = logging.Formatter(
        fmt="%(asctime)s %(levelname)-5s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    def __init__(self, name: str, log_file: str = None, stdout_level: Union[int, str] = 'INFO', log_requests: bool = True):

        """Initialize the logger

        Each Client object corresponds to a unique username/domain combination, which is used to attach it to its
        associated MagentoLogger and log file, allowing all activity across all endpoints to be tracked.
        A package logger exists as well, which logs all activity from the package.
        All log files have their log level set to DEBUG

        :param name: logger name
        :param log_file: log file name; default is {name}.log
        :param stdout_level: logging level for stdout logger; default is "INFO" (which is also logging.INFO and 10)
        :param log_requests: set to True to add logging from the requests package logger
        :note: You can control the directory where logs are saved by setting the environment variable ``MAGENTO_DEFAULT_LOG_DIR``.
           If set, all logs will be saved in that directory unless an explicit ``log_file`` is provided.
        """
        self.name = name
        self.logger = None
        self.handler_name = None

        default_log_dir = os.getenv('MAGENTO_DEFAULT_LOG_DIR')
        final_log_file = log_file if log_file else f'{self.name}.log'
        if default_log_dir:
            os.makedirs(default_log_dir, exist_ok=True)
            final_log_file = os.path.join(default_log_dir, os.path.basename(final_log_file))

        if default_log_dir and self.name == MagentoLogger.PACKAGE_LOG_NAME:
            final_log_file = os.path.join(default_log_dir, f"{MagentoLogger.PACKAGE_LOG_NAME}.log")

        self.log_file = final_log_file
        self.setup_logger(stdout_level, log_requests=log_requests)

    def setup_logger(self, stdout_level: Union[int, str] = 'INFO', log_requests: bool = True) -> bool:
        """Configures a logger and assigns it to the `logger` attribute."""
        logger = logging.getLogger(self.name)
        handler_map = LoggerUtils.map_handlers_by_name(logger)

        self.handler_name = MagentoLogger.HANDLER_NAME.format(
            name=self.name, stdout_level=stdout_level
        )

        # Add stream handler
        if self.handler_name not in handler_map['stream']:
            if len(handler_map['stream']) > 0:
                self.clear_magento_handlers(logger, handler_type=StreamHandler)
            stdout_handler = StreamHandler(stream=sys.stdout)
            stdout_handler.setFormatter(MagentoLogger.FORMATTER)
            stdout_handler.name = self.handler_name
            stdout_handler.setLevel(stdout_level)
            logger.addHandler(stdout_handler)

        # Add file handler
        if self.handler_name not in handler_map['file'] or self.log_path not in LoggerUtils.get_log_files(logger):
            if len(handler_map['file']) > 0:
                self.clear_magento_file_handlers(logger)
            f_handler = FileHandler(self.log_file)
            f_handler.setFormatter(MagentoLogger.FORMATTER)
            f_handler.name = self.handler_name
            f_handler.setLevel("DEBUG")
            logger.addHandler(f_handler)

            # Add request logging directly
            if log_requests:
                MagentoLogger.add_request_logging(f_handler)

        # Add package handler
        if self.name != MagentoLogger.PACKAGE_LOG_NAME:
            pkg_handler = MagentoLogger.get_package_handler()
            if pkg_handler:
                logger.addHandler(pkg_handler)

        logger.setLevel(logging.DEBUG)
        self.logger = logger
        return True

    def format_msg(self, msg: str) -> str:
        """Formats the :attr:`~.LOG_MESSAGE` using the specified message"""
        return MagentoLogger.LOG_MESSAGE.format(
            name=self.name,
            message=msg
        )

    def debug(self, msg):
        """Formats the :attr:`~.LOG_MESSAGE` with the specified message, then logs it with Logger.debug()"""
        return self.logger.debug(
            self.format_msg(msg)
        )

    def info(self, msg):
        """Formats the :attr:`~.LOG_MESSAGE` with the specified message, then logs it with Logger.info()"""
        return self.logger.info(
            self.format_msg(msg)
        )

    def error(self, msg):
        """Formats the :attr:`~.LOG_MESSAGE` with the specified message, then logs it with Logger.error()"""
        return self.logger.error(
            self.format_msg(msg)
        )

    def warning(self, msg):
        """Formats the :attr:`~.LOG_MESSAGE` with the specified message, then logs it with Logger.warning()"""
        return self.logger.warning(
            self.format_msg(msg)
        )

    def critical(self, msg):
        """Formats the :attr:`~.LOG_MESSAGE` with the specified message, then logs it with Logger.critical()"""
        return self.logger.critical(
            self.format_msg(msg)
        )

    @property
    def handlers(self):
        return self.logger.handlers

    @property
    def handler_names(self):
        return LoggerUtils.get_handler_names(self.logger)

    @property
    def handler_map(self):
        return LoggerUtils.map_handlers_by_name(self.logger)

    @property
    def file_handlers(self):
        return LoggerUtils.get_file_handlers(self.logger)

    @property
    def stream_handlers(self):
        return LoggerUtils.get_stream_handlers(self.logger)

    @property
    def log_files(self):
        return LoggerUtils.get_log_files(self.logger)

    @property
    def log_path(self):
        return os.path.abspath(self.log_file)

    @staticmethod
    def get_magento_handlers(logger):
        return [handler for handler in logger.handlers if MagentoLogger.owns_handler(handler)]

    @staticmethod
    def clear_magento_handlers(logger: Logger, handler_type: Union[Type[FileHandler], Type[StreamHandler]], clear_pkg: bool = False) -> None:
        """Clear all handlers from a logger that were created by MagentoLogger

        :param logger: any logger
        :param handler_type: the logging handler type to check for and remove
        :param clear_pkg: if True, will delete the package handler for writing to my-magento.log (Default is False)
        """
        for handler in MagentoLogger.get_magento_handlers(logger):
            if type(handler) == handler_type:
                if clear_pkg is True or handler != MagentoLogger.get_package_handler():
                    logger.removeHandler(handler)  # Either remove all handlers, or all but pkg handler

    @staticmethod
    def clear_magento_file_handlers(logger: Logger, clear_pkg: bool = False):
        return MagentoLogger.clear_magento_handlers(logger, FileHandler, clear_pkg)

    @staticmethod
    def clear_magento_stdout_handlers(logger: Logger, clear_pkg: bool = False):
        return MagentoLogger.clear_magento_handlers(logger, StreamHandler, clear_pkg)

    @staticmethod
    def owns_handler(handler: Handler):
        """Checks if a handler is a Stream/FileHandler from this package or not"""
        try:  # Match handler name to MagentoLogger.HANDLER_NAME format
            prefix, name, stdout_level = handler.name.split('__')
            return prefix == MagentoLogger.PREFIX
        except:  # Wrong format or not set
            return False

    @staticmethod
    def get_package_handler() -> FileHandler:
        """Returns the FileHandler object that writes to the magento.log file"""
        pkg_handlers = logging.getLogger(MagentoLogger.PACKAGE_LOG_NAME).handlers
        for handler in pkg_handlers:
            if isinstance(handler, FileHandler):
                if handler.baseFilename == os.path.abspath(MagentoLogger.PACKAGE_LOG_NAME + '.log'):
                    return handler

    @staticmethod
    def add_request_logging(handler: Union[FileHandler, StreamHandler]):
        """Adds the specified handler to the requests package logger, allowing for easier debugging of API calls"""
        if type(handler) not in (FileHandler, StreamHandler):
            raise TypeError(f"Parameter handler must be of type {FileHandler} or {StreamHandler}")

        req_logger = requests.urllib3.connectionpool.log
        req_logger.setLevel("DEBUG")
        if handler in req_logger.handlers:
            return True  # Already added

        if type(handler) is FileHandler:
            if handler.baseFilename not in LoggerUtils.get_log_files(req_logger):
                req_logger.addHandler(handler)  # Might be same handler new file (or level)

        elif type(handler) is StreamHandler:
            stdout_names = LoggerUtils.map_handlers_by_name(req_logger)['stream']
            if handler.name not in stdout_names: # Might be same handler new level
                req_logger.addHandler(handler)

        return True


def get_package_file_handler():
    return MagentoLogger.get_package_handler()
