from odoo import api, models, fields
from ..hooks import _load_xsd_complement


class ResCompany(models.Model):
    _inherit = "res.company"
    _description = 'Company'

    curp = fields.Char(
        help="Llenar en caso de que el empleador sea una persona física")
    riesgo_puesto = fields.Many2one(
        "cfdi_nomina.riesgo.puesto", string="Clase riesgo")
    registro_patronal = fields.Many2one('hr.ext.mx.regpat')
    cfd_mx_test_nomina = fields.Boolean('Timbrar en modo de prueba (nómina)')
    xs_id_region = fields.Selection(selection=[
            ('demo', 'Demo'),
            ('demo2', 'Demo2'),
        ], string='region',store=True ,default="demo")

    @api.model
    def _load_xsd_attachments(self):
        res = super()._load_xsd_attachments()
        url = 'http://www.sat.gob.mx/sitio_internet/cfd/nomina/nomina12.xsd'
        xsd = self.env.ref('l10n_mx_edi.xsd_cached_nomina12_xsd', False)
        if xsd:
            xsd.unlink()
        _load_xsd_complement(self._cr, None, url)
        return res
