# -*- coding: utf-8 -*-
##############################################################################
#    Copyright (C) 2020 AtharvERP (<http://atharverp.com/>). All Rights Reserved
#    Lifeplus, Health Care Solution
# Odoo Proprietary License v1.0
#
# This software and associated files (the "Software") may only be used (executed,
# modified, executed after modifications) if you have purchased a valid license
# from the authors, typically via Odoo Apps, atharverp.com or you have written agreement from
# author of this software owner.
#
# You may develop Odoo modules that use the Software as a library (typically
# by depending on it, importing it and using its resources), but without copying
# any source code or material from the Software. You may distribute those
# modules under the license of your choice, provided that this license is
# compatible with the terms of the Odoo Proprietary License (For example:
# LGPL, MIT, or proprietary licenses similar to this one).
#
# It is forbidden to publish, distribute, sublicense, or sell copies of the Software
# or modified copies of the Software.
#
# The above copyright notice and this permission notice must be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
# DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
# ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.
##############################################################################

from odoo import models, fields, api, _
import base64
# from odoo import tools
from odoo.exceptions import UserError
from suds.client import Client

import logging
_logger = logging.getLogger(__name__)


class AccountInvoice(models.Model):
    _inherit = 'account.move'

    id_cancel_request = fields.Char(
        'Cancellation Request ID', readonly=True, copy=False)

    @api.model
    def _l10n_mx_edi_advans_info(self, company_id, service_type):
        test = company_id.l10n_mx_edi_pac_test_env
        username = company_id.l10n_mx_edi_pac_username
        password = company_id.l10n_mx_edi_pac_password
        url = 'https://dev.advans.mx/ws/awscfdi.php?wsdl' \
            if test else 'https://app33.advans.mx/ws/awscfdi.php?wsdl'
        urlcancel = 'http://facturaloplus.com/ws/interfaz/dev33CancelacionWS.php?wsdl' \
            if test else 'http://facturaloplus.com/ws/interfaz/app33CancelacionWS.php?wsdl'
        return {
            'url': url,
            'urlcancel': urlcancel,
            'multi': False,
            'username': 'AAA010101AAA' if test else username,
            'password': '15bc268cee0e5719f5bfb8d093b90d20' if test else password,
            # 'password': '93c1f756b265f9a279aceaabe35f6612' if test else password,
        }

    def _l10n_mx_edi_advans_sign(self, pac_info):
        '''SIGN for Advans.
        '''
        url = pac_info['url']
        password = pac_info['password']
        for rec in self:
            cfdi = base64.decodebytes(
                rec.l10n_mx_edi_cfdi or b'').decode('UTF-8')
            try:
                client = Client(url, timeout=20)
                response = client.service.timbrar2(password, cfdi)
            except Exception as e:
                rec.l10n_mx_edi_log_error(str(e))
                continue
            msg = getattr(response, 'Message', None) or ''
            code = getattr(response, 'Code', None)
            xml_signed = getattr(response, 'CFDI', None) or ''
            if xml_signed:
                xml_signed = base64.b64encode(xml_signed.encode('utf-8'))

            rec._l10n_mx_edi_post_sign_process(xml_signed, code, msg)

    def _l10n_mx_edi_advans_cancel(self, pac_info):
        '''CANCEL for Advans.
        '''
        urlcancel = pac_info['urlcancel']
        password = pac_info['password']
        for invoice in self:
            uuid = invoice.l10n_mx_edi_cfdi_uui
            certificate_id = invoice.l10n_mx_edi_cfdi_certificate_id.sudo()
            cer_pem = certificate_id.get_pem_cer(
                certificate_id.content).decode('UTF-8')
            key_pem = certificate_id.get_pem_key(
                certificate_id.key, certificate_id.password).decode('UTF-8')
            receivervat = invoice.partner_id.vat
            totalinvoice = round(invoice.amount_total, 2)
            try:
                client = Client(urlcancel, timeout=20)
                if not invoice.id_cancel_request:
                    # Solicitar Cancelacion
                    response = client.service.Cancelar(
                        ApiKey=password,
                        PrivateKeyPem=key_pem,
                        PublicKeyPem=cer_pem,
                        Uuid=uuid,
                        RfcReceptor=receivervat,
                        Total=totalinvoice,
                    )
                else:
                    # Consultar cancelacion en proceso
                    response = client.service.ConsultarEstado(
                        ApiKey=password,
                        Id=invoice.id_cancel_request
                    )
            except Exception as e:
                invoice.l10n_mx_edi_log_error(str(e))
                continue
            code = getattr(response, 'Code', None)
            acuse_data = getattr(response, 'Acuse', None) or ''
            # cancelled or previously cancelled
            cancelled = code in ('201', '202')
            # no show code and response message if cancel was success
            msg = '' if cancelled else getattr(response, 'Message', None) or ''
            code = '' if cancelled else code
            id_cancel_request = getattr(response, 'Id', None) or ''
            if id_cancel_request:
                invoice.id_cancel_request = id_cancel_request
            invoice._l10n_mx_edi_post_cancel_process(cancelled, code, msg)
