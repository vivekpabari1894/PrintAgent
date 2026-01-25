from odoo import http, _
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager

class SaasPortal(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super(SaasPortal, self)._prepare_home_portal_values(counters)
        if 'saas_license_count' in counters:
            partner = request.env.user.partner_id
            values['saas_license_count'] = request.env['saas.license'].search_count([
                ('partner_id', 'child_of', partner.commercial_partner_id.id)
            ])
        return values

    @http.route(['/my/saas', '/my/saas/page/<int:page>'], type='http', auth="user", website=True)
    def portal_my_saas_licenses(self, page=1, date_begin=None, date_end=None, sortby=None, **kw):
        values = self._prepare_portal_layout_values()
        partner = request.env.user.partner_id
        SaasLicense = request.env['saas.license']

        domain = [('partner_id', 'child_of', partner.commercial_partner_id.id)]

        searchbar_sortings = {
            'date': {'label': _('Newest'), 'order': 'create_date desc'},
            'expiration': {'label': _('Expiration'), 'order': 'expiration_date asc'},
            'name': {'label': _('Name'), 'order': 'name'},
        }
        if not sortby:
            sortby = 'date'
        order = searchbar_sortings[sortby]['order']

        # Count for pager
        license_count = SaasLicense.search_count(domain)
        
        # Pager logic
        pager = portal_pager(
            url="/my/saas",
            url_args={'date_begin': date_begin, 'date_end': date_end, 'sortby': sortby},
            total=license_count,
            page=page,
            step=self._items_per_page
        )

        # search the count to display
        licenses = SaasLicense.search(
            domain,
            order=order,
            limit=self._items_per_page,
            offset=pager['offset']
        )
        
        values.update({
            'date': date_begin,
            'licenses': licenses,
            'page_name': 'saas_license',
            'default_url': '/my/saas',
            'pager': pager,
            'searchbar_sortings': searchbar_sortings,
            'sortby': sortby
        })
        return request.render("cloud_printing_saas.portal_my_saas_licenses", values)
