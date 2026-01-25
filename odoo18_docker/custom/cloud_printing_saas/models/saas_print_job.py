from odoo import models, fields

class SaasPrintJob(models.Model):
    _name = "saas.print.job"
    _description = "SaaS Print Job"

    printer_uid = fields.Char(required=True)
    content = fields.Text(string="PDF Content (Base64)", required=True)
    status = fields.Selection([
        ('queued', 'Queued'),
        ('assigned', 'Assigned'),
        ('done', 'Done'),
        ('error', 'Error')
    ], default='queued', required=True)
    license_id = fields.Many2one("saas.license", string="License", required=True, ondelete="cascade")
    partner_id = fields.Many2one(related="license_id.partner_id", store=True)   
