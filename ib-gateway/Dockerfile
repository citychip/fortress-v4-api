FROM ghcr.io/gnzsnz/ib-gateway:stable

# Patch config.ini.tmpl to suppress the write-access dialog
# The file uses CRLF line endings, so we must handle \r in the sed pattern
# ReadOnlyLogin=yes means IBC will NOT prompt for 2FA write-access confirmation
RUN sed -i "s/ReadOnlyLogin=no\r/ReadOnlyLogin=yes\r/" /home/ibgateway/ibc/config.ini.tmpl

# Verify the patch applied
RUN grep "ReadOnlyLogin" /home/ibgateway/ibc/config.ini.tmpl
