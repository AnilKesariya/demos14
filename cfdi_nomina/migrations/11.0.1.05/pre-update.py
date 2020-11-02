################################################
# Coded by: Jose Gpe Osuna joseg.osuna@gmail.com
################################################

from odoo import api, fields, models, _
from odoo import SUPERUSER_ID
import logging
_logger = logging.getLogger(__name__)


def migrate(cr, version):
    _logger.info('Migracion Iniciada')

    sql = """
    DROP TABLE IF EXISTS hr_tabla_subsidio;
    DROP TABLE IF EXISTS hr_tabla_isr;
    """
    cr.execute(sql)

    cr.commit()
    _logger.info('Migracion Terminada')


