# Base interface for identity providers.
# To be used by any connector to an identity provider.
# Attributes:
#     orgname: The human readable name of this identity provider.
#     rfid: The rfid as six-digit string.
#     user: The user object (with real data after authenticating).


class IdProvider(object):

    def __init__(self):
        pass

    @property
    def orgname(self):
        raise NotImplementedError("Attribute 'orgname' must be set by class '%s'" % self.__class__.__name__)

    # Authenticates the given legi number if possible.
    # Args:
    #     rfid: The six digit RFID number (int as str).
    # Returns:
    #     Appropiate 'user' object if authentication was successful, False otherwise.
    def auth(self, rfid):
        raise NotImplementedError("Method 'auth' must be implemented by class '%s'" % self.__class__.__name__)

    # Reports a vending from the given user.
    # Args:
    #     user: The user who got a beer (user object).
    #     slot: The slot the user chose (int).
    # Returns:
    #     True if reporting was successful, False otherwise.
    def report(self, user, slot):
        raise NotImplementedError("Method 'report' must be implemented by class '%s'" % self.__class__.__name__)


# The user object holding data about a machine user
# Attributes:
#     rfid: The six digit RFID number of the user (int as str).
#     nethz: The user's nethz identification string (str).
#     credits: The credits the user has (int).
#     name: The user's real name (str).
class User(object):

    # Creates a new user object.
    # Args:
    #     rfid: The six digit RFID number of the user (int as str).
    #     credits: The credits the user has (int).
    #     nethz: The user's nethzidentification string (str).
    #     name: The user's name (str).
    def __init__(self, rfid=None, credits=None, nethz=None, name='Student/in'):

        self.rfid = rfid
        self.credits = credits
        self.nethz = nethz
        self.name = name
