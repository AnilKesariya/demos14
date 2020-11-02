################################################
# Coded by: Jose Gpe Osuna joseg.osuna@gmail.com
################################################


import logging
_logger = logging.getLogger(__name__)


def migrate(cr, version):
    _logger.info('Migracion Iniciada')

    sql = """
    UPDATE hr_leave SET payslip_status = payslip_processed WHERE payslip_processed = TRUE;
    ALTER TABLE hr_leave DROP COLUMN payslip_processed;
    """
    cr.execute(sql)

    cr.commit()
    _logger.info('Migracion Terminada')
