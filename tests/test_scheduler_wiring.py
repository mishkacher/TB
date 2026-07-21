import unittest

from telegram.ext import Application

from alerts.scheduler import schedule_alerts, schedule_fvg_alerts


class SchedulerWiringTests(unittest.TestCase):
    def test_registers_periodic_job_with_real_telegram_application(self):
        application = Application.builder().token("123456:TEST_TOKEN").build()

        schedule_alerts(application, interval_minutes=15)

        self.assertIsNotNone(application.job_queue)
        self.assertEqual(
            len(application.job_queue.get_jobs_by_name("approved-setup-alerts")),
            1,
        )

    def test_registers_fifteen_minute_fvg_job(self):
        application = Application.builder().token("123456:TEST_TOKEN").build()

        schedule_fvg_alerts(application)

        self.assertEqual(
            len(application.job_queue.get_jobs_by_name("fvg-confirmed-control")),
            1,
        )
        self.assertEqual(
            len(application.job_queue.get_jobs_by_name("fvg-pre-control-t-minus-3")),
            1,
        )
        self.assertEqual(
            len(application.job_queue.get_jobs_by_name("fvg-rest-recovery")),
            1,
        )


if __name__ == "__main__":
    unittest.main()
