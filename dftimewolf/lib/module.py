# -*- coding: utf-8 -*-
"""Class definition for DFTimewolf modules."""

import abc
import logging
# Some AttributeErrors occurred when trying to access logging.handlers, so
# we import them separately
from logging import handlers
import traceback
import sys

from typing import Optional, TYPE_CHECKING, Type, cast, TypeVar, Dict, Any

from dftimewolf.lib import errors
from dftimewolf.lib import logging_utils
from dftimewolf.lib.containers import interface

if TYPE_CHECKING:
  # Import will only happen during type checking, disabling linter warning.
  from dftimewolf.lib import state  # pylint: disable=cyclic-import
T = TypeVar("T", bound="interface.AttributeContainer")  # pylint: disable=invalid-name,line-too-long


class BaseModule(object):
  """Interface of a DFTimewolf module.

  Attributes:
    critical (bool): True if this module is critical to the execution of
        the recipe. If set to True, and the module fails to properly run,
        the recipe will be aborted.
    name (str): A unique name for a specific instance of the module
          class. If not provided, will default to the module's class name.
    state (DFTimewolfState): recipe state.
  """

  def __init__(self,
               state: "state.DFTimewolfState",
               name:Optional[str]=None,
               critical: Optional[bool]=False):
    """Initialize a module.

    Args:
      state (DFTimewolfState): recipe state.
      name (Optional[str]): A unique name for a specific instance of the module
          class. If not provided, will default to the module's class name.
      critical (Optional[bool]): True if the module is critical, which causes
          the entire recipe to fail if the module encounters an error.
    """
    super(BaseModule, self).__init__()
    self.name = name if name else self.__class__.__name__
    self.critical = critical
    self.state = state
    self.logger = cast(logging_utils.WolfLogger,
                       logging.getLogger(name=self.name))

    self.SetupLogging()

  def SetupLogging(self) -> None:
    """Sets up stream and file logging for a specific module."""
    self.logger.setLevel(logging.DEBUG)

    file_handler = handlers.RotatingFileHandler(
        logging_utils.DEFAULT_LOG_FILE,
        maxBytes=logging_utils.MAX_BYTES,
        backupCount=logging_utils.BACKUP_COUNT)
    file_handler.setFormatter(logging_utils.WolfFormatter(colorize=False))
    self.logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    formatter = logging_utils.WolfFormatter(random_color=True)
    console_handler.setFormatter(formatter)

    self.logger.addHandler(console_handler)

  def CleanUp(self) -> None:
    """Cleans up module output to prepare it for the next module."""
    # No clean up is required.
    return

  def ModuleError(self, message: str, critical: bool=False) -> None:
    """Declares a module error.

    Errors will be stored in a DFTimewolfError error object and passed on to the
    state. Critical errors will also raise a DFTimewolfError error.

    Args:
      message (str): Error text.
      critical (Optional[bool]): True if dfTimewolf cannot recover from
          the error and should abort execution.

    Raises:
      errors.DFTimewolfError: If the error is critical and dfTimewolf
          should abort execution of the recipe.
    """
    stacktrace = None
    if sys.exc_info() != (None, None, None):
      stacktrace = traceback.format_exc()

    error = errors.DFTimewolfError(
        message, name=self.name, stacktrace=stacktrace, critical=critical)
    self.state.AddError(error)
    if critical:
      self.logger.critical(error.message)
      raise error
    self.logger.error(error.message)

  @abc.abstractmethod
  def Process(self) -> None:
    """Processes input and builds the module's output attribute.

    Modules take input information and process it into output information,
    which can in turn be ingested as input information by other modules.
    """

  @abc.abstractmethod
  def SetUp(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
    """Sets up necessary module configuration options."""

class PreflightModule(BaseModule):
  """Base class for preflight modules.

  Preflight modules are special modules that are executed synchronously before
  other modules. They are intended for modules that primarily retrieve
  attributes for other modules in a recipe, for example from a ticketing system.
  """

  @abc.abstractmethod
  def Process(self) -> None:
    """Processes input and builds the module's output attribute.

    Modules take input information and process it into output information,
    which can in turn be ingested as input information by other modules.
    """

  @abc.abstractmethod
  def SetUp(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
    """Sets up necessary module configuration options."""

  @abc.abstractmethod
  def CleanUp(self) -> None:
    """Carries out optional cleanup actions at the end of the recipe run."""

class ThreadAwareModule(BaseModule):
  """Base class for ThreadAwareModules.

  ThreadAwareModule are modules designed to handle being run in parallel.

  How to implement this class:

  * This module will be threaded based on a nominated ThreadOn container type:
  so nominated by returning the class type in GetThreadOnContainerType().

  * There are a number of static methods that you can use to run once,
  regardless of the number of threads that will run.

  * SetUp will run once.

  * Process will run N times in GetThreadPoolSize() parallel threads - N is the
  number of containers of the nominated type generated by previous modules.
  Process will be passed one container of the type specified by
  GetThreadOnContainerType().
  """

  def __init__(self,
               state: "state.DFTimewolfState",
               name: Optional[str]=None,
               critical: bool=False) -> None:
    """Initializes a ThreadAwareModule.

    Args:
      state (DFTimewolfState): recipe state.
      name (Optional[str]): The module's runtime name.
      critical (Optional[bool]): True if the module is critical, which causes
          the entire recipe to fail if the module encounters an error.
    """
    super(ThreadAwareModule, self).__init__(
        state, name=name, critical=critical)

  @abc.abstractmethod
  def PreSetUp(self) -> None:
    """Carries out optional SetUp actions that only need to be performed once,
    regardless of the number of class instantiations. Called before SetUp."""

  @abc.abstractmethod
  def PostSetUp(self) -> None:
    """Carries out optional SetUp actions that only need to be performed once,
    regardless of the number of class instantiations. Called after SetUp."""

  @abc.abstractmethod
  def PreProcess(self) -> None:
    """Carries out optional Process actions that only need to be performed
    once, regardless of the number of class instantiations. Called before
    Process."""

  # pylint: disable=arguments-differ
  @abc.abstractmethod
  def Process(self, container: interface.AttributeContainer) -> None:
    """Carry out a single process based on the input container. This will be
    run in parallel, based on the number of containers of the ThreadOn type,
    given by GetThreadOnContainerType(), up to GetThreadPoolSize() max
    simultaneous threads."""
  # pylint: enable=arguments-differ

  @abc.abstractmethod
  def PostProcess(self) -> None:
    """Carries out optional Process actions that only need to be performed
    once, regardless of the number of class instantiations. Called after
    Process."""

  @staticmethod
  @abc.abstractmethod
  def GetThreadOnContainerType() -> Type[interface.AttributeContainer]:
    """Returns the container type that this module should be threaded on."""

  @abc.abstractmethod
  def GetThreadPoolSize(self) -> int:
    """Returns the maximum number of threads for this module."""

  @staticmethod
  def KeepThreadedContainersInState() -> bool:
    """Whether to keep the containers that are used to thread on in the state,
    or pop them. Default behaviour is to keep the containers. Override this
    mthod to return false to pop them from the state."""
    return True
