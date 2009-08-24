from r2.models import populatedb
populatedb.icalendar().sync('SquidList', 'The SquidList Calendar', 'http://squidlist.com/events/link/iCalendar.php', limit=10)
