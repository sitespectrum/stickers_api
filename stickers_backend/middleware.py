from datetime import datetime

from django.core.handlers.wsgi import WSGIRequest
from django.http import JsonResponse, HttpResponse
from django.utils.deprecation import MiddlewareMixin
import traceback

from api.models import ErrorLog
from stickers_backend.settings import DEBUG
from stickers_backend import utils


class CustomException(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)


class DummyError:
    def __init__(self):
        self.id = "0"


class CustomExceptionHandlerMiddleware(MiddlewareMixin):
    ERROR_SEVERITIES = {
        "critical": [
            "MemoryError",
            "RecursionError",
            "RuntimeError",
            "OSError",
            "OverflowError",
            "AssertionError",
            "ImportError",
            "FloatingPointError",
            "SystemExit",
        ],
        "database": [
            "InterfaceError",
            "NotSupportedError",
            "IntegrityError",
            "OperationalError",
            "DataError",
            "InternalError",
            "ProgrammingError",
            "DatabaseError",
            "FieldError",
        ],
        "high": [
            "FileNotFoundError",
            "ValidationError",
            "KeyError",
            "ReferenceError",
            "NameError",
            "DoesNotExist",
        ],
        "medium": [
            "AttributeError",
            "HTTPError",
            "IndexError",
            "StopIteration",
            "ConnectionError",
        ],
        "low": [
            "TypeError",
            "ValueError",
            "TemplateDoesNotExist",
            "DeprecationWarning",
            "ZeroDivisionError",
            "EmptyPage",
        ],
    }

    def process_exception(self, request: WSGIRequest, exception):
        # Classify error severity
        error_type = type(exception).__name__
        error_severity = "unknown"
        for severity, error_types in self.ERROR_SEVERITIES.items():
            if error_type in error_types:
                error_severity = severity
                break

        # Log the error
        print(f"Error Severity: {error_severity}")
        print(f"Error Type: {error_type}")
        print("Error Message:", exception)
        print(traceback.format_exc())

        if error_severity == "critical":
            utils.panic()
        elif error_severity == "database" and error_type not in ["InterfaceError", "NotSupportedError"]:
            utils.safe()
        if error_type in ["InterfaceError", "NotSupportedError"]:
            utils.fallback()

        # Save error logs for production
        if not DEBUG:
            error_log = ErrorLog.objects.create(
                error_type=error_type,
                error_message=str(exception),
                error_traceback=traceback.format_exc() + f"\n\n{request.path}",
                error_severity=error_severity,
                error_time=datetime.now(),
                panicked=error_severity == "critical",
                safe=True if error_severity == "database" and error_type not in ["InterfaceError", "NotSupportedError"] else False,
                fallback=error_type in ["InterfaceError", "NotSupportedError"],
            )
            error_log.save()
        else:
            error_log = DummyError()
        response_data = {
            "status": "Error",
            "error": f"An internal server error occurred. The error log's ID is {error_log.id}. Please contact the administrator.",
        }
        return JsonResponse(response_data, status=500)

