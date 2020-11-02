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
    UPDATE hr_employee SET sueldo_imss_bimestre_actual = ps.sdi_last
    FROM (
    SELECT hr_employee.id AS e_id,ps.sdi_last, max(ps.date_to)
    FROM hr_employee
    INNER JOIN hr_payslip AS ps ON ps.employee_id = hr_employee.id
    WHERE ps.sdi_last > 0
    GROUP BY hr_employee.id,ps.sdi_last, ps.date_to
    ) AS ps  
    WHERE ps.e_id = hr_employee.id
    """
    cr.execute(sql)

    cr.execute(sql)

    cr.commit()
    _logger.info('Migracion Terminada')


