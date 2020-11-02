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
    UPDATE hr_employee SET status_imss = 'baja'
    WHERE fecha_baja IS NOT NULL;
    """.format(superuser=SUPERUSER_ID)
    cr.execute(sql)

    sql = """
    DELETE FROM hr_employee_historico_imss WHERE round(sueldo_old ::numeric,2) = round(sueldo_new::numeric,2)
    """
    cr.execute(sql)

    cr.commit()
    _logger.info('Migracion Terminada')


