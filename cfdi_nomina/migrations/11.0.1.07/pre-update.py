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
    UPDATE hr_employee SET tipo_cuenta = '02' WHERE tipo_cuenta = '01';
    UPDATE hr_employee SET tipo_cuenta = '03' WHERE tipo_cuenta = '40';
    """
    cr.execute(sql)

    cr.commit()
    _logger.info('Migracion Terminada')


