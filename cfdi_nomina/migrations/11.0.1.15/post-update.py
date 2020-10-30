################################################
# Coded by: Jose Gpe Osuna joseg.osuna@gmail.com
################################################

from odoo import api, fields, models, _, SUPERUSER_ID
import logging
_logger = logging.getLogger(__name__)


def migrate(cr, version):
    _logger.info('Migracion Iniciada 15')
    # from dateutil import relativedelta
    # from datetime import datetime
    # from ast import literal_eval
    #
    # env = api.Environment(cr, SUPERUSER_ID, {})
    #
    # payslip_anuales = env['hr.payslip'].search([('tipo_calculo', '=', 'anual')])
    # total = len(payslip_anuales)
    # i = 0
    # for slip in payslip_anuales:
    #     i += 1
    #     _logger.info("({}/{}) {}".format(i, total, slip.name))
    #     slip.calculate_sdi_last()

    _logger.info('Migracion Terminada')


