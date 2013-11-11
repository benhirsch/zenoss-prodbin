##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

"""
Application/daemon related stuff.
"""

from zope.interface import Interface, Attribute


class IApplicationLog(Interface):
    """
    For reading a Zenoss application's log.
    """

    def last(count):
        """
        Returns a sequence containing the last count lines of the log.

        :rtype IApplicationLogInfo: The log data.
        """


class IApplication(Interface):
    """
    For controlling and inspecting Zenoss applications.
    """

    name = Attribute("Name of the application")
    description = Attribute("Brief description of the application's function")
    autostart = Attribute("True if the application will run on startup")
    state = Attribute("Current running state of the application")
    startedAt = Attribute("When the application was started")
    log = Attribute("The IApplicationLog object")
    configuration = Attribute("The application configuration object")

    def start():
        """
        Starts the application.
        """

    def stop():
        """
        Stops the application.
        """

    def restart():
        """
        Restarts the application.
        """


class IApplicationManager(Interface):
    """
    For identifying and locating Zenoss applications.
    """

    def query(name=None):
        """
        Returns a sequence of IApplication objects that match the
        given expression.  If no expression is provided, then all
        objects are returned.
        """

    def get(id, default=None):
        """
        Retrieve the IApplication object of the identified application.
        The default argument is returned if the application doesn't exist.
        """


def _makeEnumObj(name):
    return type(
        "_AppRunStateEnum", (object,), 
        { "__str__": lambda self: name }
    )()


class ApplicationState(object):

    STOPPED = _makeEnumObj("STOPPED")
    STARTING = _makeEnumObj("STARTING")
    RUNNING = _makeEnumObj("RUNNING")
    STOPPING = _makeEnumObj("STOPPING")
    RESTARTING = _makeEnumObj("RESTARTING")


del _makeEnumObj
