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
    UPDATE hr_payslip SET registro_patronal_codigo = rp.name
    FROM hr_ext_mx_regpat AS rp, res_company AS c
    WHERE rp.id = c.registro_patronal AND hr_payslip.company_id = c.id;
    """.format(superuser=SUPERUSER_ID)
    cr.execute(sql)

    cr.execute(sql)

    cr.commit()
    _logger.info('Migracion Terminada')


