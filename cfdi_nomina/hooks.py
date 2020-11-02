import base64
import logging
from os.path import join

import requests
from lxml import etree, objectify

from odoo import SUPERUSER_ID, api, tools

_logger = logging.getLogger(__name__)


def post_init_hook(cr, registry):
    url = 'http://www.sat.gob.mx/sitio_internet/cfd/nomina/nomina12.xsd'
    _load_xsd_complement(cr, registry, url)


def _load_xsd_complement(cr, registry, url):
    db_fname = _load_xsd_files(cr, registry, url)
    env = api.Environment(cr, SUPERUSER_ID, {})
    xsd = env.ref('l10n_mx_edi.xsd_cached_cfdv33_xsd', False)
    if not xsd:
        return False
    complement = {
        'namespace':
        'http://www.sat.gob.mx/nomina12',
        'schemaLocation': db_fname,
    }
    node = etree.Element('{http://www.w3.org/2001/XMLSchema}import',
                         complement)
    res = objectify.fromstring(base64.decodebytes(xsd.datas))
    res.insert(0, node)
    xsd_string = etree.tostring(res, pretty_print=True)
    xsd.datas = base64.encodebytes(xsd_string)
    return True


def _load_xsd_files(cr, registry, url):
    fname = url.split('/')[-1]
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        res = objectify.fromstring(response.content)
    except (requests.exceptions.HTTPError, etree.XMLSyntaxError) as e:
        logging.getLogger(__name__).info(
            'I cannot connect with the given URL or you are trying to load an '
            'invalid xsd file.\n%s', e.message)
        return ''
    namespace = {'xs': 'http://www.w3.org/2001/XMLSchema'}
    sub_urls = res.xpath('//xs:import', namespaces=namespace)
    for s_url in sub_urls:
        s_url_catch = _load_xsd_files(
            cr, registry, s_url.get('schemaLocation'))
        s_url.attrib['schemaLocation'] = s_url_catch
    try:
        xsd_string = etree.tostring(res, pretty_print=True)
    except etree.XMLSyntaxError:
        logging.getLogger(__name__).info('XSD file downloaded is not valid')
        return ''
    env = api.Environment(cr, SUPERUSER_ID, {})
    xsd_fname = 'xsd_cached_%s' % fname.replace('.', '_')
    attachment = env.ref('l10n_mx_edi.%s' % xsd_fname, False)
    filestore = tools.config.filestore(cr.dbname)
    if attachment:
        return join(filestore, attachment.store_fname)
    attachment = env['ir.attachment'].create({
        'name': xsd_fname,
        # 'datas_fname': fname,
        'datas': base64.encodebytes(xsd_string),
    })
    attachment._inverse_datas()
    cr.execute(
        """INSERT INTO ir_model_data (name, res_id, module, model)
           VALUES (%s, %s, 'l10n_mx_edi', 'ir.attachment')""",
        (xsd_fname, attachment.id))
    return join(filestore, attachment.store_fname)
