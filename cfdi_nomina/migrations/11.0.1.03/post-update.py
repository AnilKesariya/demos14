################################################
# Coded by: Jose Gpe Osuna joseg.osuna@gmail.com
################################################

import odoo
from odoo import api, fields, models, _
from odoo import SUPERUSER_ID
import logging
_logger = logging.getLogger(__name__)


def migrate(cr, version):
    _logger.info('Migracion Iniciada')

    env = api.Environment(cr, SUPERUSER_ID, {})
    tabla_vac_id = env.ref('cfdi_nomina.hr_holiday_id').id
    sql = """
    UPDATE hr_employee SET tabla_vacaciones_id = %d WHERE tabla_vacaciones_id IS NULL
    """ % tabla_vac_id
    cr.execute(sql)

    cr.commit()
    _logger.info('Migracion Terminada')


