## The contents of this file are subject to the Common Public Attribution
## License Version 1.0. (the "License"); you may not use this file except in
## compliance with the License. You may obtain a copy of the License at
## http://code.reddit.com/LICENSE. The License is based on the Mozilla Public
## License Version 1.1, but Sections 14 and 15 have been added to cover use of
## software over a computer network and provide for limited attribution for the
## Original Developer. In addition, Exhibit A has been modified to be consistent
## with Exhibit B.
## 
## Software distributed under the License is distributed on an "AS IS" basis,
## WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License for
## the specific language governing rights and limitations under the License.
## 
## The Original Code is Reddit.
## 
## The Original Developer is the Initial Developer.  The Initial Developer of
## the Original Code is CondeNet, Inc.
## 
## All portions of the code written by CondeNet are Copyright (c) 2006-2009
## CondeNet, Inc. All Rights Reserved.
################################################################################
<%!
   from r2.lib.template_helpers import get_domain
   from r2.lib.strings import Score
 %>

<%namespace file="buttontypes.html" import="submiturl" />

<% 
    domain = get_domain()
    if thing._fullname:
        path = thing.make_permalink_slow()
    else:
        path = capture(submiturl, thing.url, thing.title)
%>
(function() {
       
    var styled_submit = '<a style="color: #369; text-decoration: none;" href="${path}" target="${thing.target}">';
    var unstyled_submit = '<a href="${submiturl(thing.url)}" target="${path}">';
    var write_string='<span class="reddit_button" style="';
%if thing.styled:    
    write_string += 'color: grey;';
%endif
    write_string += '">';
%if thing.image > 0:
    write_string += unstyled_submit + '<img style="height: 2.3ex; vertical-align:top; margin-right: 1ex" src="http://${get_domain(subreddit=False)}/static/spreddit${thing.image}.gif">' + "</a>";
%endif
%if thing._fullname:
    write_string += '${Score.safepoints(thing.score)}';
    %if thing.styled:  
        write_string += ' on ' + styled_submit + 'reddit</a>';
    %else:
        write_string += ' on ' + unstyled_submit + 'reddit</a>';
    %endif
%else:
    %if thing.styled:
    write_string += styled_submit + 'submit';
    %else:
    write_string += unstyled_submit + 'submit';
    %endif
    %if thing.image > 0:
    write_string += '</a>';
    %else:
    write_string += ' to reddit</a>';
    %endif
%endif
    write_string += '</span>';

document.write(write_string);
})()
