import datetime

#Copied PSTx from populatedb.py master-jesse branch
#Original commit: http://github.com/rajbot/tikical/commit/060c068f0bc5dc52d7c1b3150a4461d94d32f0bd#diff-6
class PSTx(datetime.tzinfo):
	def utcoffset(self, dt):
		return datetime.timedelta(hours=8) + self.dst(dt)
	def _FirstSunday(self, dt):
		return dt+datetime.timedelta(days=(6-dt.weekday()))
	def dst(self, dt):
		dst_start = self._FirstSunday(datetime.datetime(dt.year, 3, 8, 2))
		dst_end = self._FirstSunday(datetime.datetime(dt.year, 11, 1, 1))
		if dst_start <= dt.replace(tzinfo=None) < dst_end:
			return datetime.timedelta(hours=1)
		else:
			return datetime.timedelta(hours=0)
	def tzname(self, dt):
		return self.dst(dt) == datetime.timedelta(hours=0) and 'PST' or 'PDT'