from guillotina import configure
from guillotina import permissions


# Add new permission
configure.permission('guillotina.ManageAMQP', 'Manage guillotina amqp endpoints')

# Grant it to guillotina.Manager
configure.grant(
    permission='guillotina.ManageAMQP',
    role='guillotina.Manager')
