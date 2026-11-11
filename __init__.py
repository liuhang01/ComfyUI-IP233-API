from .ip233.nodes import (
    IP233Config, IP233ModelInfo, IP233ImageParameters, IP233VideoParameters,
    IP233ImageSubmit, IP233VideoSubmit, IP233ResumeTask, IP233TaskStatus,
    IP233TaskWait, IP233ImageResult, IP233VideoResult, IP233UploadImage,
)

NODE_CLASS_MAPPINGS = {
    "IP233Config": IP233Config,
    "IP233ModelInfo": IP233ModelInfo,
    "IP233ImageParameters": IP233ImageParameters,
    "IP233VideoParameters": IP233VideoParameters,
    "IP233ImageSubmit": IP233ImageSubmit,
    "IP233VideoSubmit": IP233VideoSubmit,
    "IP233ResumeTask": IP233ResumeTask,
    "IP233TaskStatus": IP233TaskStatus,
    "IP233TaskWait": IP233TaskWait,
    "IP233ImageResult": IP233ImageResult,
    "IP233VideoResult": IP233VideoResult,
    "IP233UploadImage": IP233UploadImage,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "IP233Config": "IP233 API Config",
    "IP233ModelInfo": "IP233 Model Info",
    "IP233ImageParameters": "IP233 Image Parameters",
    "IP233VideoParameters": "IP233 Video Parameters",
    "IP233ImageSubmit": "IP233 Image Generate / Edit",
    "IP233VideoSubmit": "IP233 Video Generate",
    "IP233ResumeTask": "IP233 Resume Task",
    "IP233TaskStatus": "IP233 Task Status",
    "IP233TaskWait": "IP233 Wait for Task",
    "IP233ImageResult": "IP233 Image Result",
    "IP233VideoResult": "IP233 Video Result",
    "IP233UploadImage": "IP233 Upload Reference Images",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
