# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import timedelta
import datetime
from odoo import api, fields, models, _
from odoo.exceptions import UserError
import math
import logging
_logger = logging.getLogger(__name__)


def float_to_time(float_hour):
    return datetime.time(int(math.modf(float_hour)[1]), int(60 * math.modf(float_hour)[0]), 0)


class HrAttendanceReport(models.AbstractModel):
    _name = 'report.cfdi_nomina.attendance_report'

    @api.model
    def _get_report_values(self, docids, data=None):
        if not data.get('form'):
            raise UserError(_("Form content is missing, this report cannot be printed."))

        data = data.get('form')
        employees = self.env['hr.employee'].browse(data['emp'])
        return {
            'doc_ids': self.ids,
            'doc_model': 'hr.employee',
            'docs': employees,
            'get_range_days': self._get_range_days(
                data['date_from'], data['date_to']),
            'get_attendance_day': self._get_attendance_day,
        }

    @api.model
    def get_timedelta_tz(self, day=None, user=None):
        if not user:
            user = self.env.user
        if not day:
            day = datetime.datetime.now()
        ahora_tz = fields.Datetime.context_timestamp(
            self.with_context(tz=(user.partner_id.tz or 'America/Mexico_City')), day)
        tz_horas_diff = ahora_tz.tzinfo._utcoffset  # timedelta
        return tz_horas_diff

    def _get_range_days(self, date_from, date_to):

        date_from = fields.Datetime.from_string(date_from)
        date_to = fields.Datetime.from_string(date_to)

        days = []
        for day in range(0, (date_to - date_from).days + 1):
            days.append(fields.Date.to_string(date_from))
            date_from += timedelta(1)
        return days

    def _get_attendance_day(self, daystr, employee):

        day = fields.Datetime.from_string(daystr)
        tz_horas_diff = self.get_timedelta_tz(day=day)
        date_from = day - tz_horas_diff
        date_to = datetime.datetime.combine(day, datetime.time.max) - tz_horas_diff

        # Ofix repite check_in y  check_out en una misma checada
        attendances = employee.attendance_ids.search([
            ('id', 'in', employee.attendance_ids.ids),
            ('check_in', '>=', str(date_from)), ('check_in', '<=', str(date_to))],
            order='check_in')

        attendances_list = [fields.Datetime.from_string(a.check_in) + tz_horas_diff for a in attendances]

        weekday = day.weekday()
        horario_rst = self.env['resource.calendar.attendance'].search([
            ('dayofweek', '=', weekday),
            ('calendar_id', '=', employee.resource_calendar_id.id)],
            order='hour_from ASC'
        )

        attendances_list, ausencias = self.env['hr.attendance.gen.wiz'].get_checadas_validas_dia(
            attendances_list, day, employee, horario_rst)

        total = 0
        if len(attendances_list) >= 2 and all(attendances_list[0:2]):
            total = (attendances_list[1] - attendances_list[0]).seconds
        if len(attendances_list) >= 4 and all(attendances_list[2:4]):
            total += (attendances_list[3] - attendances_list[2]).seconds

        return {
            'check': attendances_list,
            'total': total
        }
        # return [[a.check_in, a.check_out] for a in attendances]



