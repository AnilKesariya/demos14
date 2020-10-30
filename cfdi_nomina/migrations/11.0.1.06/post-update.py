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
    UPDATE hr_leave SET retardo_parent_id = parent_id WHERE parent_id IS NOT Null;
    UPDATE hr_leave SET parent_id = Null;
    """
    cr.execute(sql)

    cr.commit()
    _logger.info('Migracion Terminada')


