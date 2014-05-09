GMusic-Fuse
===========

Fuse filesystem for Google Music

Configuration
-----------

To authenticate with the Google Music services you need to provide your usename, password and a valid device id authed with your google account.

The configuration should be provided in a file called cred.conf in the same folder as the script.

    [credentials]
    username = username
    password = password

    [device]
    deviceid = device id

If you use two factor authentication you need to provide the script with a valid one time password.