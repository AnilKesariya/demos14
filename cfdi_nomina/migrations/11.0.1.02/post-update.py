################################################
# Coded by: Jose Gpe Osuna joseg.osuna@gmail.com
################################################

import logging
import odoo
_logger = logging.getLogger(__name__)


def migrate(cr, installed_version):
    _logger.info('Migracion Iniciada')

    sql = """
    DROP TABLE IF EXISTS hr_tabla_factor_integracion
    """
    cr.execute(sql)

    cr.commit()
    _logger.info('Migracion Terminada')


# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
