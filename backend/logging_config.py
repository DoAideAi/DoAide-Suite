"""Keep bearer links out of HTTP access logs."""
import logging
import re


def redact_path(path):
    path=re.sub(r'(/api/(?:portal|contractor)/)[^/? ]+',r'\1[redacted]',str(path))
    return re.sub(r'([?&](?:token|portal|invite|task|hub\.verify_token)=)[^& ]+',r'\1[redacted]',path)


class PrivateAccessFilter(logging.Filter):
    def filter(self,record):
        if isinstance(record.args,tuple) and len(record.args)>=3:
            args=list(record.args);args[2]=redact_path(args[2]);record.args=tuple(args)
        return True


def install_private_access_logging():
    logger=logging.getLogger('uvicorn.access')
    if not any(isinstance(f,PrivateAccessFilter) for f in logger.filters):logger.addFilter(PrivateAccessFilter())
