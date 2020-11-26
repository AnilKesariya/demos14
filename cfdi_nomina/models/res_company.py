from odoo import api, models, fields
from ..hooks import _load_xsd_complement


class ResCompany(models.Model):
    _inherit = "res.company"
    _description = 'Company'

    curp = fields.Char(
        help="Fill out in case the employer is a natural person")
    riesgo_puesto = fields.Many2one(
        "cfdi_nomina.riesgo.puesto", string="Risk class")
    registro_patronal = fields.Many2one('hr.ext.mx.regpat')
    cfd_mx_test_nomina = fields.Boolean('Ring in test mode (payroll)')
    xs_id_region = fields.Selection(selection=[
            ('shallows', 'Bajío'),
            ('center 1', 'Centro 1'),
            ('center 2', 'Centro 2'),
            ('gulf', 'Golfo'),
            ('northeast', 'Noreste'),
            ('south','Sur'),
            ('southeast','Sureste'),
        ], string='Region',store=True ,default="shallows")
    warehouse = fields.Text(string="ID Warehouse")

    @api.model
    def _load_xsd_attachments(self):
        res = super()._load_xsd_attachments()
        url = 'http://www.sat.gob.mx/sitio_internet/cfd/nomina/nomina12.xsd'
        xsd = self.env.ref('l10n_mx_edi.xsd_cached_nomina12_xsd', False)
        if xsd:
            xsd.unlink()
        _load_xsd_complement(self._cr, None, url)
        return res
