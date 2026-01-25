from odoo import http, fields
from odoo.http import request
import json
import logging
_logger = logging.getLogger(__name__)

class SaasController(http.Controller):

    # ---------------------------
    # Helper: License Validation
    # ---------------------------
    def _get_license(self, key):
        if not key:
            return None
        return request.env['saas.license'].sudo().search([
            ('name', '=', key),
        ], limit=1)

    def _check_license(self, request, key):
        """
        Validates license and returns (record, error_response).
        If record is present, error_response is None.
        If record is None or invalid, error_response is a werkzeug Response.
        """
        if not key:
             return None, request.make_response(
                 json.dumps({'error': 'Missing License Key', 'code': 'missing_key'}), 
                 headers={'Content-Type': 'application/json'}, 
                 status=401
             )
        
        license_rec = self._get_license(key)
        
        if not license_rec:
             return None, request.make_response(
                 json.dumps({'error': 'Invalid License Key', 'code': 'invalid_key'}), 
                 headers={'Content-Type': 'application/json'}, 
                 status=403
             )
             
        if license_rec.state != 'active':
             return None, request.make_response(
                 json.dumps({'error': 'License Expired or Inactive', 'code': 'expired_key'}), 
                 headers={'Content-Type': 'application/json'}, 
                 status=403
             )
             
        return license_rec, None

    # ---------------------------
    # Agent Endpoints
    # ---------------------------

    @http.route('/api/agent/printers', type='json', auth='public', methods=['POST'], csrf=False)
    def register_printers(self, **kwargs):
        """
        Agent registers printers.
        Headers/Payload should contain license_key.
        """
        # Note: When type='json', request.jsonrequest contains the body
        data = request.jsonrequest
        # Odoo's JSON-RPC wrapper might put params in 'params', but pure JSON POST to this route works if formatted right.
        # However, to be compatible with standard REST agents (requests.post(json=...)), 
        # we might need type='http' and manual parsing if we want pure JSON body control.
        # BUT, let's try to stick to "Params" if possible, or parse standard body.
        
        # Actually, for non-Odoo-client consumption, type='http' is often easier to control input/output format.
        # But let's try to support the JSON-RPC style or check if we can seamlessy handle it.
        # The existing agent uses requests.post(json=...). Odoo's type='json' expects { "jsonrpc": "2.0", "params": ... } usually.
        # To support "raw" JSON, we should use type='http' and parse request.httprequest.data
        pass 
        # Wait, I will reimplement this AS type='http' to perfectly match the existing Agent's REST behavior.
        return self._register_printers_http()

    @http.route('/api/agent/printers', type='http', auth='public', methods=['POST'], csrf=False)
    def _register_printers_http(self, **kwargs):
        try:
            payload = json.loads(request.httprequest.data)
            headers = request.httprequest.headers
            license_key = headers.get('X-License-Key')
            
            license_rec, error_response = self._check_license(request, license_key)
            if error_response:
                return error_response
            
            server_uid = payload.get("server_uid", "default")
            
            # Enforce Server Limit
            # Count unique servers currently registered (excluding this one if it exists)
            Printers = request.env['saas.printer'].sudo()
            existing_servers = Printers.read_group(
                [('license_id', '=', license_rec.id)],
                ['server_uid'],
                ['server_uid']
            )
            # existing_server_ids is a list of unique UIDs
            known_uids = [g['server_uid'] for g in existing_servers]
            
            if server_uid not in known_uids:
                if len(known_uids) >= license_rec.server_limit:
                    return request.make_response(
                        json.dumps({'error': f'Plan Limit Reached. Max {license_rec.server_limit} Print Servers allowed.', 'code': 'limit_reached'}), 
                        headers={'Content-Type': 'application/json'}, 
                        status=403
                    )

            # Clean up old printers for this agent + license
            Printers.search([
                ('server_uid', '=', server_uid),
                ('license_id', '=', license_rec.id)
            ]).unlink()
            
            for p_item in payload.get("printers", []):
                uid = p_item.get("os_id") or p_item.get("uid") if isinstance(p_item, dict) else p_item
                name = p_item.get("name") if isinstance(p_item, dict) else p_item
                
                if uid and name:
                    Printers.create({
                        'name': name,
                        'uid': uid,
                        'server_uid': server_uid,
                        'license_id': license_rec.id
                    })
            
            return request.make_response(json.dumps({'ok': True}), headers={'Content-Type': 'application/json'})
        except Exception as e:
            return request.make_response(json.dumps({'error': str(e)}), headers={'Content-Type': 'application/json'}, status=500)

    @http.route('/api/agent/jobs', type='http', auth='public', methods=['GET'], csrf=False)
    def fetch_jobs(self, **kwargs):
        try:
            headers = request.httprequest.headers
            license_key = headers.get('X-License-Key')
            
            license_rec, error_response = self._check_license(request, license_key)
            if error_response:
                return error_response
            
            # Update Last Seen for this Agent's printers
            server_id = headers.get('X-Server-ID')
            if server_id:
                printers_to_update = request.env['saas.printer'].sudo().search([
                    ('license_id', '=', license_rec.id),
                    ('server_uid', '=', server_id)
                ])
                _logger.info(f"AGENT PING: License={license_key}, Server={server_id}, Found Printers={len(printers_to_update)}")
                printers_to_update.write({'last_poll': fields.Datetime.now()})
            else:
                 _logger.warning(f"AGENT PING (No Server ID): License={license_key}")
            
            Jobs = request.env['saas.print.job'].sudo()
            job = Jobs.search([
                ('status', '=', 'queued'),
                ('license_id', '=', license_rec.id)
            ], limit=1, order='create_date asc')
            
            if not job:
                 return request.make_response(json.dumps(None), headers={'Content-Type': 'application/json'})
            
            # Assign
            job.write({'status': 'assigned'})
            request.env.cr.commit() # Important to lock/save state immediately to avoid double fetch
            
            return request.make_response(json.dumps({
                'job_id': job.id,
                'printer_uid': job.printer_uid,
                'content': job.content
            }), headers={'Content-Type': 'application/json'})

        except Exception as e:
            return request.make_response(json.dumps({'error': str(e)}), headers={'Content-Type': 'application/json'}, status=500)

    @http.route('/api/jobs/status', type='http', auth='public', methods=['POST'], csrf=False)
    def update_job_status(self, **kwargs):
        try:
            payload = json.loads(request.httprequest.data)
            headers = request.httprequest.headers
            license_key = headers.get('X-License-Key')
            
            license_rec, error_response = self._check_license(request, license_key)
            if error_response:
                return error_response
            
            job_id = payload.get('job_id')
            status = payload.get('status')
            
            job = request.env['saas.print.job'].sudo().browse(job_id)
            if job.exists() and job.license_id.id == license_rec.id:
                job.write({'status': status})
                return request.make_response(json.dumps({'ok': True}), headers={'Content-Type': 'application/json'})
            
            return request.make_response(json.dumps({'error': 'Job not found'}), headers={'Content-Type': 'application/json'}, status=404)
        except Exception as e:
            return request.make_response(json.dumps({'error': str(e)}), headers={'Content-Type': 'application/json'}, status=500)

    # ---------------------------
    # Client Endpoints
    # ---------------------------

    @http.route('/api/printers', type='http', auth='public', methods=['GET'], csrf=False)
    def notes_client_fetch_printers(self, **kwargs):
        try:
            headers = request.httprequest.headers
            license_key = headers.get('X-License-Key')
            
            license_rec, error_response = self._check_license(request, license_key)
            if error_response:
                return error_response
            
            server_uid = kwargs.get('server_uid')
            domain = [('license_id', '=', license_rec.id)]
            if server_uid:
                domain.append(('server_uid', '=', server_uid))
                
            printers = request.env['saas.printer'].sudo().search(domain)
            
            data = []
            now = fields.Datetime.now()
            limit = fields.Datetime.subtract(now, minutes=2)
            
            for p in printers:
                status = 'offline'
                if p.last_poll and p.last_poll > limit:
                    status = 'online'
                data.append({
                    'uid': p.uid, 
                    'name': p.name, 
                    'server_uid': p.server_uid,
                    'status': status
                })
            
            return request.make_response(json.dumps(data), headers={'Content-Type': 'application/json'})
        except Exception as e:
            return request.make_response(json.dumps({'error': str(e)}), headers={'Content-Type': 'application/json'}, status=500)

    @http.route('/api/print/jobs', type='http', auth='public', methods=['POST'], csrf=False)
    def client_create_job(self, **kwargs):
        try:
            payload = json.loads(request.httprequest.data)
            
            headers = request.httprequest.headers
            license_key = headers.get('X-License-Key')
            
            license_rec, error_response = self._check_license(request, license_key)
            if error_response:
                return error_response
            
            job = request.env['saas.print.job'].sudo().create({
                'printer_uid': payload.get('printer_uid'),
                'content': payload.get('content'),
                'status': 'queued',
                'license_id': license_rec.id
            })
            
            # Increment Usage Count
            license_rec.sudo().write({'print_count': license_rec.print_count + 1})
            
            return request.make_response(json.dumps({'job_id': job.id}), headers={'Content-Type': 'application/json'})
        except Exception as e:
            return request.make_response(json.dumps({'error': str(e)}), headers={'Content-Type': 'application/json'}, status=500)
    
    # Original Validation Endpoint (Kept for sanity)
    @http.route('/api/saas/validate_license', type='json', auth='public', methods=['POST'], csrf=False)
    def validate_license(self, **kwargs):
        license_key = kwargs.get('license_key')
        license_rec = self._get_license(license_key)
        
        if license_rec and license_rec.state == 'active':
            return {
                "valid": True,
                "partner_name": license_rec.partner_id.name,
                "partner_id": license_rec.partner_id.id,
                "expiration": license_rec.expiration_date
            }
        
        return {"valid": False, "error": "Invalid or expired license"}
