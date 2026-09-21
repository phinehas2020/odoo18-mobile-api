from unittest.mock import patch
from odoo.tests.common import TransactionCase, tagged
from odoo.exceptions import UserError


@tagged('post_install', '-at_install')
class TestActionRecovery(TransactionCase):
    def test_handler_created_receipt_is_reused(self):
        service = self.env['mobile.sync.service']
        def dispatch(_service, device_id, action):
            self.env['mobile.outbox.receipt'].create({
                'device_id': device_id, 'event_id': action['event_id'],
                'status': 'success', 'model': 'stock.move.line', 'res_id': 99,
            })
            return {'status': 'success'}
        with patch.object(type(service), '_dispatch_action', dispatch):
            results = service.handle_actions('test-device', [{'event_id': 'test-receipt-reuse', 'type': 'inventory.scan'}])
        self.assertEqual(results[0]['status'], 'success')
        self.assertEqual(results[0]['event_id'], 'test-receipt-reuse')
        receipt = self.env['mobile.outbox.receipt'].search([('event_id', '=', 'test-receipt-reuse')])
        self.assertEqual(len(receipt), 1)
        self.assertEqual(receipt.res_id, 99)

    def test_conflicted_action_does_not_abort_following_action(self):
        service = self.env['mobile.sync.service']
        def dispatch(_service, device_id, action):
            if action['event_id'] == 'test-conflict':
                raise UserError('Refresh this record first')
            return {'status': 'success'}
        with patch.object(type(service), '_dispatch_action', dispatch):
            results = service.handle_actions('test-device', [
                {'event_id': 'test-conflict', 'type': 'inventory.scan'},
                {'event_id': 'test-next', 'type': 'inventory.scan'},
            ])
        self.assertEqual([result['status'] for result in results], ['failed', 'success'])
        self.assertEqual([result['event_id'] for result in results], ['test-conflict', 'test-next'])
