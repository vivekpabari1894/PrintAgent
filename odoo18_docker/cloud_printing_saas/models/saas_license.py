from odoo import models, fields, api
import uuid

class SaasLicense(models.Model):
    _name = "saas.license"
    _description = "Cloud Printing License"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(string="License Key", required=True, copy=False, readonly=True, default=lambda self: str(uuid.uuid4()))
    partner_id = fields.Many2one("res.partner", string="Customer", required=True)
    active = fields.Boolean(default=True)
    expiration_date = fields.Date(string="Expiration Date")
    # For Odoo 16+ Subscription integration, we might link to sale.order
    subscription_id = fields.Many2one("sale.order", string="Sale Order Source")
    recurring_subscription_id = fields.Many2one("sale.subscription", string="Subscription Contract")
    
    # Usage Tracking
    print_count = fields.Integer(string="Total Pages Printed", default=0, readonly=True)
    server_limit = fields.Integer(string="Max Print Servers", default=1, help="Maximum number of unique agents allowed to connect.")
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled')
    ], default='draft', string="Status", compute="_compute_state", store=True)

    @api.depends('active', 'expiration_date')
    def _compute_state(self):
        today = fields.Date.today()
        for record in self:
            if not record.active:
                record.state = 'cancelled'
            elif record.expiration_date and record.expiration_date < today:
                record.state = 'expired'
            else:
                record.state = 'active'

    def action_generate_key(self):
        for record in self:
            record.name = str(uuid.uuid4())

    def _cron_check_expirations(self):
        # Logic to auto-expire or notify
        pass
