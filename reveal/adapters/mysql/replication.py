"""MySQL replication status monitoring."""

from typing import Dict, Any


class ReplicationMonitor:
    """Monitors MySQL replication status.

    Detects master/slave role and provides replication health information
    including lag, I/O and SQL thread status, and connected slaves.
    """

    def __init__(self, connection):
        """Initialize with MySQL connection.

        Args:
            connection: MySQLConnection instance
        """
        self.conn = connection

    def get_replication(self) -> Dict[str, Any]:
        """Get replication status.

        Returns:
            Dict with role (Master/Slave/Standalone) and replication details
        """
        slave_status = self.conn.execute_single("SHOW SLAVE STATUS")
        if slave_status:
            return {
                'type': 'replication',
                'role': 'Slave',
                'master_host': slave_status.get('Master_Host'),
                'master_port': slave_status.get('Master_Port'),
                'io_running': slave_status.get('Slave_IO_Running'),
                'sql_running': slave_status.get('Slave_SQL_Running'),
                'seconds_behind_master': slave_status.get('Seconds_Behind_Master'),
                'last_error': slave_status.get('Last_Error') or 'None',
            }

        slave_hosts = self.conn.execute_query("SHOW SLAVE HOSTS")
        if slave_hosts:
            return {
                'type': 'replication',
                'role': 'Master',
                'slaves': [
                    {
                        'server_id': s.get('Server_id'),
                        'host': s.get('Host')
                    }
                    for s in slave_hosts
                ],
            }

        return {
            'type': 'replication',
            'role': 'Standalone',
            'message': 'No replication configured',
        }
