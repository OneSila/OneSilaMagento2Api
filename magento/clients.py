from __future__ import annotations
import json
import pickle
import requests
from functools import cached_property
from typing import Optional, Dict, List
from requests import Session
from requests.adapters import HTTPAdapter
from urllib3 import Retry

from .constants import Scope, StoreCode, AuthenticationMethod
from .decorators import jsondecode_error_retry
from .managers.attribute_set import AttributeSetManager
from .managers.product import ProductAttributeOptionManager, MediaEntryManager
from .managers.tax import TaxClassManager
from .utils import MagentoLogger, get_agent, parse_domain
from .models import APIResponse, ProductAttribute, Product
from .managers import Manager, OrderManager, ProductManager, InvoiceManager, CategoryManager, ProductAttributeManager, OrderItemManager, CustomerManager, \
    ShipmentManager
from .exceptions import AuthenticationError, MagentoError


class Client:

    """The class that handles all interaction with the API"""

    def __init__(
            self,
            domain: str,
            username: Optional[str] = None,
            password: Optional[str] = 'my-magento-client',
            api_key: Optional[str] = None,
            scope: Optional[str] = '',
            local: bool = False,
            user_agent: Optional[str] = None,
            log_level: str = 'INFO',
            login: bool = True,
            strict_mode: bool = True,
            authentication_method: AuthenticationMethod = AuthenticationMethod.PASSWORD.value,
            **kwargs
    ):
        """Initialize a Client

        .. admonition:: Important!
           :class: important-af

           The Magento account you use to log in must be assigned a **User Role** that has
           the appropriate API resources included in its **Resource Access** settings

           This can be verified in Magento Admin by going to::

            System -> Permissions -> User Roles -> {Role} -> Role Resources -> Resource Access

           and ensuring that ``Sales``, ``Catalog``, ``Customers``, and any other desired resources are included


        :param domain: domain name of the Magento store (ex. ``domain.com`` or ``127.0.0.1/magento24``)
        :param username: username of the Magento Admin account
        :param password: password of the Magento Admin account
        :param api_key: api key from the Magento Integration Section
        :param scope: the store view scope to :meth:`~search` and make requests on
        :param local: whether the Magento store is hosted locally
        :param user_agent: the user agent to use in requests
        :param log_level: the logging level for logging to stdout
        :param login: if ``True``, calls :meth:`~.authenticate` upon initialization
        :param kwargs: see below
        :param strict_mode: if ``True``, raises exceptions on operation failures; if ``False``, only logs errors
        :param authentication_type: WE can chose if we want to authenticate via username & password / api key
        ...

        :Extra Keyword Arguments:
            * **log_file** (``str``) – log file to use for the client's :attr:`logger`
            * **log_requests** (``bool``) - if ``True``, the logs from :mod:`requests`
              will be added to the client's ``log_file``\

        IMPORTANT!: If authentication with access token (api_key) doesn't work try this:
        Login to Admin >> Stores >> Stores >> Settings >> Configuration >> SERVICES
        >> Magento Web API >> Web API Security >> Allow Anonymous Guest Access: Yes
                           >> OAuth >> Allow OAuth Access Tokens to be used as standalone Bearer token: Yes
        """
        #: The base API URL
        self.BASE_URL: str = ("http" if local else "https") + f"://{parse_domain(domain)}/rest/V1/"
        #: The user credentials
        self.USER_CREDENTIALS: Dict[str, Optional[str]] = {
            'username': username,
            'password': password
        }
        #: The api key (if provided)
        self.api_key: Optional[str] = api_key
        #: Authentication method
        self.authentication_method: AuthenticationMethod = authentication_method
        #: The Magento store domain
        self.domain: str = domain
        #: The store view code to request/update data on
        self.scope: str = scope
        #: The user agent to use in requests
        self.user_agent: str = user_agent if user_agent else get_agent()
        #: The :class:`~.MagentoLogger` for the domain/username combination
        self.logger: MagentoLogger = self.get_logger(
            stdout_level=log_level,
            log_file=kwargs.get('log_file', None),
            log_requests=kwargs.get('log_requests', True)
        )
        #: An initialized :class:`Store` object
        self.store: Store = Store(self)
        #: If strict_mode is True, raise exceptions on failures, otherwise only log errors
        self.strict_mode: bool = strict_mode
        # the current number of authentication retries
        self.authentication_retries = 0

        self.session = Session()
        retries = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[502, 503, 504],
            allowed_methods={'POST', 'PUT'},
        )
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount('https://', adapter)

        if login:
            self.authenticate()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.session.close()

    @classmethod
    def new(cls) -> Client:
        """Prompts for input to log in to the Magento API"""
        return cls(
            input('Domain: '),
            input('Username: '),
            input('Password: ')
        )

    @classmethod
    def load(cls, pickle_bytes: bytes) -> Client:
        """Initialize a :class:`~.Client` using a pickle bytestring from :meth:`~.to_pickle`"""
        return pickle.loads(pickle_bytes)

    @classmethod
    def from_json(cls, json_str: str) -> Client:
        """Initialize a :class:`~.Client` from a JSON string of settings"""
        return cls.from_dict(json.loads(json_str))

    @classmethod
    def from_dict(cls, d: dict) -> Client:
        """Initialize a :class:`~.Client` from a dictionary of settings"""
        return cls(**d)

    def url_for(self, endpoint: str, scope: str = None) -> str:
        """Returns the appropriate request url for the given API endpoint and store scope

        .. admonition:: Example
            :class: example

            ::

             # Generate the url for credit memo with id 7
             >> api=Client("domain.com", "user", "password")
             >> api.url_for('creditmemo/7')
             "https://domain.com/rest/V1/creditmemo/7"

             # Generate the same url on the "en" store view
             >> api.url_for('creditmemo/7', scope='en')
             "https://domain.com/rest/en/V1/creditmemo/7"

        :param endpoint: the API endpoint
        :param scope: the scope to generate the url for; uses the :attr:`.Client.scope` if not provided
        """
        if not scope:
            if self.scope and scope is None:
                scope = self.scope
            else:
                return self.BASE_URL + endpoint
        return self.BASE_URL.replace('/V1', f'/{scope}/V1') + endpoint

    def manager(self, endpoint: str) -> Manager:
        """Initializes and returns a :class:`~.Manager` corresponding to the specified endpoint

        .. note:: Several endpoints have predefined :class:`~.Manager` and :class:`~.Model` subclasses

           If a subclass hasn't been defined for the ``endpoint`` yet, a general :class:`~.Manager`
           will be returned, which wraps the :attr:`~.Manager.result` with :class:`~.APIResponse`

        :param endpoint: a valid Magento API search endpoint
        """
        if endpoint.lower() == 'orders':
            return self.orders
        if endpoint.lower() == 'orders/items':
            return self.order_items
        if endpoint.lower() == 'invoices':
            return self.invoices
        if endpoint.lower() == 'taxes':
            return self.taxes
        if endpoint.lower() == 'categories':
            return self.categories
        if endpoint.lower() == 'products':
            return self.products
        if endpoint.lower() == 'products/attributes':
            return self.product_attributes
        if endpoint.lower() == 'products/attribute-sets' or endpoint.lower() == 'products/attribute-sets/list':
            return self.product_attribute_set
        if endpoint.lower() == 'shipment' or endpoint.lower() == 'shipments':
            return self.shipments
        if endpoint.lower() in ('customers', 'customers/search'):
            return self.customers
        if 'products/attributes' in endpoint.lower() and '/options' in endpoint.lower():
            return self.product_attribute_options
        if 'products/' in endpoint.lower() and '/media' in endpoint.lower():
            return self.product_media_entries
        # Any other endpoint is queried with a general Manager object
        return Manager(endpoint=endpoint, client=self)

    @property
    def orders(self) -> OrderManager:
        """Initializes an :class:`~.OrderManager`"""
        return OrderManager(self)

    @property
    def taxes(self) -> TaxClassManager:
        """Initializes an :class:`~.TaxClassManager`"""
        return TaxClassManager(self)

    @property
    def order_items(self) -> OrderItemManager:
        """Initializes an :class:`~.OrderItemManager`"""
        return OrderItemManager(self)

    @property
    def invoices(self) -> InvoiceManager:
        """Initializes an :class:`~.InvoiceManager`"""
        return InvoiceManager(self)

    @property
    def categories(self) -> CategoryManager:
        """Initializes a :class:`~.CategoryManager`"""
        return CategoryManager(self)

    @property
    def products(self) -> ProductManager:
        """Initializes a :class:`~.ProductManager`"""
        return ProductManager(self)

    @property
    def product_attributes(self) -> ProductAttributeManager:
        """Initializes a :class:`~.ProductAttributeManager`"""
        return ProductAttributeManager(self)

    @property
    def product_attribute_set(self) -> AttributeSetManager:
        """Initializes a :class:`~.ProductAttributeManager`"""
        return AttributeSetManager(self)

    @property
    def shipments(self) -> ShipmentManager:
        """Initializes a :class:`~.ProductAttributeManager`"""
        return ShipmentManager(self)

    @property
    def product_attribute_options_attribute(self) -> Optional[ProductAttribute]:
        """Get or set the ProductAttribute required for the ProductAttributeOptionManager."""
        if hasattr(self, '_product_attribute_options_attribute'):
            return self._product_attribute_options_attribute
        return None

    @product_attribute_options_attribute.setter
    def product_attribute_options_attribute(self, attribute: ProductAttribute) -> None:
        """Set the ProductAttribute required for the ProductAttributeOptionManager."""
        # Clear the _product_attribute_options to ensure it's reinitialized with the new attribute
        if hasattr(self, '_product_attribute_options'):
            del self._product_attribute_options

        self._product_attribute_options_attribute = attribute

    @property
    def product_attribute_options(self) -> ProductAttributeOptionManager:
        """Return the ProductAttributeOptionManager if the attribute has been set, otherwise raise an error."""
        if not hasattr(self, '_product_attribute_options') or self._product_attribute_options is None:
            if not hasattr(self, '_product_attribute_options_attribute') or self._product_attribute_options_attribute is None:
                raise AttributeError(
                    "Attribute was not set for this manager to work. Please set `product_attribute_options_attribute` first."
                )

        self._product_attribute_options = ProductAttributeOptionManager(client=self, attribute=self._product_attribute_options_attribute)
        return self._product_attribute_options

    @property
    def media_entries_product(self) -> Optional[Product]:
        """Get or set the Product required for the MediaEntryManager."""
        if hasattr(self, '_media_entries_product'):
            return self._media_entries_product
        return None

    @media_entries_product.setter
    def media_entries_product(self, product: Product) -> None:
        """Set the Product required for the MediaEntryManager."""
        # Clear the _media_entry_manager to ensure it's reinitialized with the new product
        if hasattr(self, '_media_entry_manager'):
            del self._media_entry_manager

        self._media_entries_product = product

    @property
    def product_media_entries(self) -> MediaEntryManager:
        """Return the MediaEntryManager if the product has been set, otherwise raise an error."""
        if not hasattr(self, '_media_entry_manager') or self._media_entry_manager is None:
            if not hasattr(self, '_media_entries_product') or self._media_entries_product is None:
                raise AttributeError(
                    "Product was not set for this manager to work. Please set `media_entries_product` first."
                )

        self._media_entry_manager = MediaEntryManager(client=self, product=self._media_entries_product)
        return self._media_entry_manager

    @property
    def customers(self) -> CustomerManager:
        """Initializes a :class:`~.CustomerManager`"""
        return CustomerManager(self)

    def get(self, url: str) -> requests.Response:
        """Sends an authorized ``GET`` request

        :param url: the URL to make the request on
        """
        return self.request('GET', url)

    def post(self, url: str, payload: dict) -> requests.Response:
        """Sends an authorized ``POST`` request

        :param url: the URL to make the request on
        :param payload: the JSON payload for the request
        """
        return self.request('POST', url, payload)

    def put(self, url: str, payload: dict) -> requests.Response:
        """Sends an authorized ``PUT`` request

        :param url: the URL to make the request on
        :param payload: the JSON payload for the request
        """
        return self.request('PUT', url, payload)

    def delete(self, url: str) -> requests.Response:
        """Sends an authorized ``DELETE`` request

        :param url: the URL to make the request on
        """
        return self.request('DELETE', url)

    def authenticate(self) -> bool:
        """Authenticates the :attr:`~.USER_CREDENTIALS` and retrieves an access token
        """
        if self.authentication_retries == 3:
            raise ValueError('Max attends of authentication attempts exceeded')
        self.authentication_retries += 1

        if self.USER_CREDENTIALS['password'] is None and self.api_key is None:
            raise ValueError('Ether password or api key must be provided.')

        if self.authentication_method == AuthenticationMethod.TOKEN.value:
            self.ACCESS_TOKEN = self.api_key
        else:
            endpoint = self.url_for('integration/admin/token')
            payload = self.USER_CREDENTIALS
            headers = {
                'Content-Type': 'application/json',
                'User-Agent': self.user_agent
            }
            self.logger.info(f'Authenticating {payload["username"]} on {self.domain}...')
            response = requests.post(
                url=endpoint,
                json=payload,
                headers=headers
            )
            if response.ok:
                self.ACCESS_TOKEN = response.json()
            else:
                raise AuthenticationError(self, response=response)

        self.logger.debug('Validating token...')
        try:
            self.validate()
        except AuthenticationError as e:
            raise AuthenticationError(self, msg='Token validation failed') from e

        self.logger.info('Authenticated successfully to {}'.format(self.domain))
        self.authentication_retries = 0
        return True

    def validate(self) -> bool:
        """Validates the :attr:`~.token` by sending an authorized request to a standard API endpoint

        :raises: :class:`~.AuthenticationError` if the token is invalid
        """
        response = self.get(self.url_for('store/websites'))
        if response.status_code == 200:
            self.logger.debug("Token validated for {} on {}".format(
                self.USER_CREDENTIALS['username'], self.domain))
            return True
        else:
            msg = "Token validation failed for {} on {}".format(
                self.USER_CREDENTIALS['username'], self.domain)
            raise AuthenticationError(self, msg=msg, response=response)

    @jsondecode_error_retry()
    def request(self, method: str, url: str, payload: dict = None) -> requests.Response:
        """Sends an authorized API request. Used for all internal requests

        .. tip:: Use :meth:`get`, :meth:`post`, :meth:`put` or :meth:`delete` instead

        :param method: the request method
        :param url: the url to send the request to
        :param payload: the JSON payload for the request (if the method is ``POST`` or ``PUT``)
        """

        method = method.upper()
        if method in ('GET', 'DELETE'):
            response = self.session.request(method, url, headers=self.headers)
        elif method in ('POST', 'PUT'):
            if payload:
                response = self.session.request(method, url, json=payload, headers=self.headers)
            else:
                raise ValueError('Must provide a non-empty payload')
        else:
            raise ValueError('Invalid request method provided')

        if response.status_code == 401:
            self.logger.debug("Attempting to re-authenticate...")
            self.authenticate()  # Will raise AuthenticationError if unsuccessful (won't recurse infinitely)
            return self.request(method, url, payload)


        if response.status_code != 200:  # All non 401 responses are returned; errors are logged then handled by methods
            self.logger.error("Request to {} failed with status code {}.\n{message}".format(
                url, response.status_code, message=MagentoError.parse(response))
            )

        return response

    def get_logger(self, log_file: str = None, stdout_level: str = 'INFO', log_requests: bool = True) -> MagentoLogger:
        """Retrieve a MagentoLogger for the current username/domain combination. Log files are DEBUG.

        :param log_file: the file to log to
        :param stdout_level: the logging level for stdout logging
        :param log_requests: if ``True``, adds the :class:`~.FileHandler` to the :mod:`~.urllib3.connectionpool` logger
        """
        logger_name = MagentoLogger.CLIENT_LOG_NAME.format(
            domain=self.BASE_URL.split('://')[-1].split('/')[0].replace('.', '_'),
            username=self.USER_CREDENTIALS['username']
        )   # Example:``domain_username``
        return MagentoLogger(
            name=logger_name,
            log_file=log_file,
            stdout_level=stdout_level,
            log_requests=log_requests
        )

    @property
    def headers(self) -> dict:
        """Authorization headers for API requests

        Automatically generates a :attr:`token` if needed
        """
        return {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json',
            'User-Agent': self.user_agent
        }

    @property
    def token(self) -> str:
        """Returns or generates an :attr:`~ACCES_TOKEN`"""
        if not self.ACCESS_TOKEN:
            self.authenticate()
        return self.ACCESS_TOKEN

    def to_pickle(self, validate: bool = False) -> bytes:
        """Serializes the Client to a pickle bytestring

        :param validate: if ``True``, validates the :attr:`token`/:attr:`USER_CREDENTIALS` before serializing
        """
        if validate:
            self.validate()
        return pickle.dumps(self)

    def to_json(self, validate: bool = False) -> str:
        """Serializes the Client to a JSON string

        :param validate: if ``True``, validates the :attr:`token`/:attr:`USER_CREDENTIALS` before serializing
        """
        data = self.to_dict(validate)
        return json.dumps(data)

    def to_dict(self, validate: bool = False) -> Dict[str, str]:
        """Serializes the Client to a dictionary

        :param validate: if ``True``, validates the :attr:`token`/:attr:`USER_CREDENTIALS` before serializing
        """
        if validate:
            self.validate()
        data = {
            'domain': self.domain,
            'username': self.USER_CREDENTIALS['username'],
            'password': self.USER_CREDENTIALS['password'],
            'scope': self.scope,
            'user_agent': self.user_agent,
            'token': self.token,
            'log_level': self.logger.logger.level,
            'log_file': self.logger.log_file
        }
        return data

    def view_config(self):
        """Prints the Client configuration settings"""
        for k, v in self.to_dict().items():
            print(f'{k} : {v}')


class Store:

    """Class containing store configurations and cached attribute lists"""

    def __init__(self, client: Client):
        """Initialize a Store object

        :param client: an initialized :class:`~.Client` object
        """
        self.client = client

    @property
    def is_single_store(self) -> bool:
        """Whether the store has a single store view (``default``) or multiple store views"""
        return len(self.configs) == 1

    @property
    def active(self) -> APIResponse:
        """Returns the store config corresponding to the current :attr:`~.Client.scope` of the :class:`Client`"""
        store_code = StoreCode.DEFAULT.value if self.client.scope in ('', StoreCode.ALL.value) else self.client.scope
        for store in self.configs:
            if store.code == store_code:
                return store

        if store_code == StoreCode.DEFAULT.value:  # If custom store code is used for default view, use config with the smallest ID
            return sorted(self.configs, key=lambda config: config.id)[0]


    @cached_property
    def configs(self) -> Optional[APIResponse | List[APIResponse]]:
        """Returns a list of all store configurations"""
        return self.client.manager('store/storeConfigs').execute_search()

    @cached_property
    def views(self) -> Optional[APIResponse | List[APIResponse]]:
        """Returns a list of all store views"""
        return self.client.manager('store/storeViews').execute_search()

    @cached_property
    def websites(self) -> Optional[APIResponse | List[APIResponse]]:
        """Returns a list of all store views"""
        return self.client.manager('store/websites').execute_search()

    @cached_property
    def all_product_attributes(self) -> List[ProductAttribute]:
        """A cached list of all product attributes"""
        return self.client.product_attributes.all_in_memory()

    @cached_property
    def store_view_product_attributes(self) -> List[ProductAttribute]:
        """A cached list of all product attributes with the ``Store View`` scope"""
        return [attr for attr in self.all_product_attributes if attr.scope == Scope.STORE.value]

    @cached_property
    def website_product_attributes(self) -> List[ProductAttribute]:
        """A cached list of all product attributes with the ``Web Site`` scope"""
        return [attr for attr in self.all_product_attributes if attr.scope == Scope.WEBSITE.value]

    @cached_property
    def global_product_attributes(self) -> List[ProductAttribute]:
        """A cached list of all product attributes with the ``Global`` scope"""
        return [attr for attr in self.all_product_attributes if attr.scope == Scope.GLOBAL.value]

    @cached_property
    def website_attribute_codes(self) -> List[str]:
        """The attribute codes of the :attr:`~.website_product_attributes`"""
        return [attr.attribute_code for attr in self.website_product_attributes]

    def filter_website_attrs(self, attribute_data: dict) -> dict:
        """Filters a product attribute dict and returns a new one that contains only the website scope attributes

        Website scoped attributes must be updated on the admin by making a second request on the ``all`` scope

        * This method is called by :meth:`~.Product.update_attributes` and :meth:`~.Product.update_custom_attributes`
          to see if the second request is needed

        .. admonition:: **Example**
           :class: example

           The ``price`` attribute is ``Website`` scope and the ``meta_title`` attribute is ``Store View`` scope

           ::

            >> attribute_data = {'price': 12, 'meta_title': 'My Product'}
            >> store.filter_website_attrs(attribute_data)
            {'price': 12}

        :param attribute_data: a dict of product attributes
        """
        return {k: v for k, v in attribute_data.items() if k in self.website_attribute_codes}

    def refresh(self) -> bool:
        """Clears all cached properties"""
        cached = ('configs', 'views', 'all_product_attributes', 'store_view_product_attributes',
                  'website_product_attributes', 'global_product_attributes', 'website_attribute_codes')
        for key in cached:
            self.__dict__.pop(key, None)
        return True
