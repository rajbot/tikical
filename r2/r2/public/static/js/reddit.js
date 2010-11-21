function open_menu(menu) {
    $(menu).siblings(".drop-choices").not(".inuse")
        .css("top", menu.offsetHeight + 'px')
                .each(function(){
                        $(this).css("left", $(menu).position().left + "px")
                            .css("top", ($(menu).height()+
                                         $(menu).position().top) + "px");
                    })
        .addClass("active inuse");
};

function close_menus() {
    $(".drop-choices.inuse").not(".active")
        .removeClass("inuse");
    $(".drop-choices.active").removeClass("active");
};

function hover_open_menu(menu) { };

function update_user(form) {
  try {
    var user = $(form).find("input[name=user]").val();
    form.action += "/" + user;
  } catch (e) {
    // ignore
  }

  return true;
}

function post_user(form, where) {
  var user = $(form).find("input[name=user]").val();

  if (user == null) {
    return post_form (form, where);
  } else {
    return post_form (form, where + '/' + user);
  }
}

function post_form(form, where, statusfunc, nametransformfunc, block) {
    try {
        if(statusfunc == null)
            statusfunc = function(x) { 
                return reddit.status_msg.submitting; 
            };
        /* set the submitted state */
        $(form).find(".error").not(".status").hide();
        $(form).find(".status").html(statusfunc(form)).show();
        return simple_post_form(form, where, {}, block);
    } catch(e) {
        return false;
    }
};

function get_form_fields(form, fields) {
    fields = fields || {};
    /* consolidate the form's inputs for submission */
    $(form).find("select, input, textarea").not(".gray, :disabled").each(function() {
            if (($(this).attr("type") != "radio" &&
                 $(this).attr("type") != "checkbox") ||
                $(this).attr("checked"))
                fields[$(this).attr("name")] = $(this).attr("value");
        });
    if (fields.id == null) {
        fields.id = $(form).attr("id") ? ("#" + $(form).attr("id")) : "";
    }
    return fields;
};

function simple_post_form(form, where, fields, block) {
    $.request(where, get_form_fields(form, fields), null, block);
    return false;
};


function emptyInput(elem, msg) {
    if (! $(elem).attr("value") || $(elem).attr("value") == msg ) 
        $(elem).addClass("gray").attr("value", msg).attr("rows", 3);
    else
        $(elem).focus(function(){});
};


function showlang() {
    $(".lang-popup:first").show();
    return false;
};

function showcover(warning, reason) {
    $.request("new_captcha");
    if (warning) 
        $("#cover_disclaim, #cover_msg").show();
    else
        $("#cover_disclaim, #cover_msg").hide();
    $(".login-popup:first").show()
        .find("form input[name=reason]").attr("value", (reason || ""));
    
    return false;
};

function hidecover(where) {
    $(where).parents(".cover-overlay").hide();
    return false;
};

/* table handling */

function deleteRow(elem) {
    $(elem).delete_table_row();
};



/* general things */

function change_state(elem, op, callback) {
    var form = $(elem).parents("form");
    /* look to see if the form has an id specified */
    var id = form.find("input[name=id]");
    if (id.length) 
        id = id.attr("value");
    else /* fallback on the parent thing */
        id = $(elem).thing_id();

    simple_post_form(form, op, {id: id});
    /* call the callback first before we mangle anything */
    if (callback) callback(form, op);
    form.html(form.attr("executed").value);
    return false;
};

function save_thing(elem) {
    $(elem).thing().addClass("saved");
}

function unsave_thing(elem) {
    $(elem).thing().removeClass("saved");
}

function hide_thing(elem) {
    var thing = $(elem).thing();
    thing.hide();
    if(thing.hasClass("hidden"))
        thing.removeClass("hidden");
    else
        thing.addClass("hidden");
};

function toggle_label (elem, callback, cancelback) {
  $(elem).parent().find(".option").toggle();
  $(elem).onclick = function() {
    return(toggle_label(elem, cancelback, callback));
  }
  if (callback) callback(elem);
}

function toggle(elem, callback, cancelback) {
    var self = $(elem).parent().andSelf().filter(".option");
    var sibling = self.removeClass("active")
        .siblings().addClass("active").get(0); 

    /*
    var self = $(elem).siblings().andSelf();
    var sibling = self.filter(":hidden").debug();
    self = self.filter(":visible").removeClass("active");
    sibling = sibling.addClass("active").get(0);
    */

    if(cancelback && !sibling.onclick) {
        sibling.onclick = function() {
            return toggle(sibling, cancelback, callback);
        }
    }
    if(callback) callback(elem);
    return false;
};

function cancelToggleForm(elem, form_class, button_class, on_hide) {
    /* if there is a toggle button that triggered this, toggle it if
     * it is not already active.*/
    if(button_class && $(elem).filter("button").length) {
        var sel = $(elem).thing().find(button_class)
            .children(":visible").filter(":first");
        toggle(sel);
    }
    $(elem).thing().find(form_class)
        .each(function() {
                if(on_hide) on_hide($(this));
                $(this).hide().remove();
            });
    return false;
};

/* organic listing */

function get_organic(elem, next) {
    var listing = $(elem).parents(".organic-listing");
    var thing = listing.find(".thing:visible");
    if(listing.find(":animated").length) 
        return false;
    
    /* note we are looking for .thing.link while empty entries (if the
     * loader isn't working) will be .thing.stub -> no visual
     * glitches */
    var next_thing;
    if (next) {
        next_thing = thing.nextAll(".thing:not(.stub)").filter(":first");
        if (next_thing.length == 0)
            next_thing = thing.siblings(".thing:not(.stub)").filter(":first");
    }
    else {
        next_thing = thing.prevAll(".thing:not(.stub)").filter(":first");
        if (next_thing.length == 0)
            next_thing = thing.siblings(".thing:not(.stub)").filter(":last");
    }    
    thing.fadeOut('fast', function() {
            if(next_thing.length)
                next_thing.fadeIn('fast', function() {

                        /* make sure the next n are loaded */
                        var n = 5;
                        var t = thing;
                        var to_fetch = [];
                        for(var i = 0; i < 2*n; i++) {
                            t = (next) ? t.nextAll(".thing:first") : 
                                t.prevAll(".thing:first"); 
                            if(t.length == 0) 
                                t = t.end().parent()
                                    .children( (next) ? ".thing:first" : 
                                               ".thing:last");
                            if(t.filter(".stub").length)
                                to_fetch.push(t.thing_id());
                            if(i >= n && to_fetch.length == 0)
                                break;
                        }
                        if(to_fetch.length) {
                            $.request("fetch_links",  
                                      {links: to_fetch.join(','),
                                              listing: listing.attr("id")}); 
                        }
                    })
                    });
};

/* links */

function linkstatus(form) {
    return reddit.status_msg.submitting;
};


function subscribe(reddit_name) {
    return function() { 
        if (!reddit.logged)  {
            showcover();
        } else {
            $.things(reddit_name).find(".entry").addClass("likes");
            $.request("subscribe", {sr: reddit_name, action: "sub"});
        }
    };
};

function unsubscribe(reddit_name) {
    return function() { 
        if (!reddit.logged)  {
            showcover();
        } else {
            $.things(reddit_name).find(".entry").removeClass("likes");
            $.request("subscribe", {sr: reddit_name, action: "unsub"});
        }
    };
};

function friend(user_name, container_name, type) {
    return function() {
        $.request("friend", 
                  {name: user_name, container: container_name, type: type});
    }
};

function unfriend(user_name, container_name, type) {
    return function() {
        $.request("unfriend", 
                  {name: user_name, container: container_name, type: type});
    }
};

function share(elem) {
    $.request("new_captcha");
    $(elem).new_thing_child($(".sharelink:first").clone(true)
                            .attr("id", "sharelink_" + $(elem).thing_id()),
                             false);
    $.request("new_captcha");
};

function cancelShare(elem) {
    return cancelToggleForm(elem, ".sharelink", ".share-button");
};

/* Comment generation */
function helpon(elem) {
    $(elem).parents(".usertext-edit:first").children(".markhelp:first").show();
};
function helpoff(elem) {
    $(elem).parents(".usertext-edit:first").children(".markhelp:first").hide();
};

function hidecomment(elem) {
    $(elem).thing().hide()
        .find(".noncollapsed:first, .midcol:first, .child:first").hide().end()
        .show().find(".entry:first .collapsed").show();
    return false;
};

function showcomment(elem) {
    var comment = $(elem).thing();
    comment.find(".entry:first .collapsed").hide().end()
        .find(".noncollapsed:first, .midcol:first, .child:first").show().end()
        .show();
    return false;
};

function morechildren(form, link_id, children, depth) {
    $(form).html(reddit.status_msg.loading)
        .css("color", "red");
    var id = $(form).parents(".thing.morechildren:first").thing_id();
    $.request('morechildren', {link_id: link_id,
                children: children, depth: depth, id: id});
    return false;
};

/* stylesheet and CSS stuff */

function update_reddit_count(site) {
    if (!site || !reddit.logged) return;
    
    var decay_factor = .9; //precentage to keep
    var decay_period = 86400; //num of seconds between updates
    var num_recent = 10; //num of recent reddits to report
    var num_count = 100; //num of reddits to actually count
    
    var date_key = '_date';
    var cur_date = new Date();
    var count_cookie = 'reddit_counts';
    var recent_cookie = 'recent_reddits';
    var reddit_counts = $.cookie_read(count_cookie).data;
    
    //init the reddit_counts dict
    if (!$.defined(reddit_counts) ) {
        reddit_counts = {};
        reddit_counts[date_key] = cur_date.toString();
    }
    var last_reset = new Date(reddit_counts[date_key]);
    var decay = cur_date - last_reset > decay_period * 1000;

    //incrmenet the count on the current reddit
    reddit_counts[site] = $.with_default(reddit_counts[site], 0) + 1;

    //collect the reddit names (for sorting) and decay the view counts
    //if necessary
    var names = [];
    $.each(reddit_counts, function(sr_name, value) {
            if(sr_name != date_key) {
                if (decay && sr_name != site) {
                    //compute the new count val
                    var val = Math.floor(decay_factor * reddit_counts[sr_name]);
                    if (val > 0) 
                        reddit_counts[sr_name] = val;
                    else 
                        delete reddit_counts[sr_name];
                }
                if (reddit_counts[sr_name]) 
                    names.push(sr_name);
            }
        });

    //sort the names by the view counts
    names.sort(function(n1, n2) {
            return reddit_counts[n2] - reddit_counts[n1];
        });

    //update the last decay date
    if (decay) reddit_counts[date_key] = cur_date.toString();

    //build the list of names to report as "recent"
    var recent_reddits = "";
    for (var i = 0; i < names.length; i++) {
        var sr_name = names[i];
        if (i < num_recent) {
            recent_reddits += names[i] + ',';
        } else if (i >= num_count && sr_name != site) {
            delete reddit_counts[sr_name];
        }
    }

    //set the two cookies: one for the counts, one for the final
    //recent list
    $.cookie_write({name: count_cookie, data: reddit_counts});
    if (recent_reddits) 
        $.cookie_write({name: recent_cookie, data: recent_reddits});
};


function add_thing_to_cookie(thing, cookie_name) {
    var id = $(thing).thing_id();

    if(id && id.length) {
        return add_thing_id_to_cookie(id, cookie_name);
    }
}

function add_thing_id_to_cookie(id, cookie_name) {
    var cookie = $.cookie_read(cookie_name);
    if(!cookie.data) {
        cookie.data = "";
    }

    /* avoid adding consecutive duplicates */
    if(cookie.data.substring(0, id.length) == id) {
        return;
    }

    cookie.data = id + ',' + cookie.data;

    if(cookie.data.length > 1000) {
        var fullnames = cookie.data.split(',');
        fullnames = $.uniq(fullnames, 20);
        cookie.data = fullnames.join(',');
    }

    $.cookie_write(cookie);
};

function clicked_items() {
    var cookie = $.cookie_read('recentclicks2');
    if(cookie && cookie.data) {
        var fullnames = cookie.data.split(",");
        /* don't return empty ones */
        for(var i=fullnames.length-1; i >= 0; i--) {
            if(!fullnames[i] || !fullnames[i].length) {
                fullnames.splice(i,1);
            }
        }
        return fullnames;
    } else {
        return [];
    }
}

function clear_clicked_items() {
    var cookie = $.cookie_read('recentclicks2');
    cookie.data = '';
    $.cookie_write(cookie);
    $('.gadget').remove();
}

function updateEventHandlers(thing) {
    /* this function serves as a default callback every time a new
     * Thing is inserted into the DOM.  It serves to rewrite a Thing's
     * event handlers depending on context (as in the case of an
     * organic listing) and to set the click behavior on links. */
    thing = $(thing);
    var listing = thing.parent();

    $(thing).filter(".promotedlink").bind("onshow", function() {
            var id = $(this).thing_id();
            if($.inArray(id, reddit.tofetch) != -1) {
                $.request("onload", {ids: reddit.tofetch.join(",")});
                reddit.tofetch = [];
            }
            var tracker = reddit.trackers[id]; 
            if($.defined(tracker)) {
                $(this).find("a.title").attr("href", tracker.click).end()
                    .find("img.promote-pixel")
                    .attr("src", tracker.show);
                delete reddit.trackers[id];
            }
        })
        /* pre-trigger new event if already shown */
        .filter(":visible").trigger("onshow");

    /* click on a title.. */
    $(thing).filter(".link")
        .find("a.title, a.comments").mousedown(function() {
            /* the site is either stored in the sr dict, or we are on
             * an sr and it is the current one */
            var sr = reddit.sr[$(this).thing_id()] || reddit.cur_site;
            update_reddit_count(sr);
            /* mark as clicked */
            $(this).addClass("click");
            /* set the click cookie. */
            add_thing_to_cookie(this, "recentclicks2");
            /* remember this as the last thing clicked */
            var wasorganic = $(this).parents('.organic-listing').length > 0;
            last_click(thing, wasorganic);
        });

    if (listing.filter(".organic-listing").length) {
        thing.find(".hide-button a, .del-button a.yes, .report-button a.yes")
            .each(function() { $(this).get(0).onclick = null });
        thing.find(".hide-button a")
           .click(function() {
                   var a = $(this).get(0);
                   change_state(a, 'hide', 
                                function() { get_organic(a, 1); });
                });
        thing.find(".del-button a.yes")
            .click(function() {
                    var a = $(this).get(0);
                    change_state(a, 'del', function() { get_organic(a, 1); });
                });
        thing.find(".report-button a.yes")
            .click(function() {
                    var a = $(this).get(0);
                    change_state(a, 'report', 
                                 function() { get_organic(a, 1); });
                    }); 

        /*thing.find(".arrow.down")
            .one("click", function() {
                    var a = $(this).get(0);
                    get_organic($(this).get(0), 1);
                    }); */
    }
};

function last_click(thing, organic) {
  /* called with zero arguments, marks the last-clicked item on this
     page (to which the user probably clicked the 'back' button in
     their browser). Otherwise sets the last-clicked item to the
     arguments passed */
  var cookie = "last_thing";
  if(thing) {
    var data = {href: window.location.href, 
                what: $(thing).thing_id(),
                organic: organic};
    $.cookie_write({name: cookie, data: data});
  } else {
    var current = $.cookie_read(cookie).data;
    if(current && current.href == window.location.href) {
      /* if they got there organically, make sure that it's in the
         organic box */
      var olisting = $('.organic-listing');
      if(current.organic && olisting.length == 1) {
        if(olisting.find('.thing:visible').thing_id() == current.what) {
          /* if it's available in the organic box, *and* it's the one
             that's already shown, do nothing */

        } else {
          var thing = olisting.things(current.what);

          if(thing.length > 0 && !thing.hasClass('stub')) {
            /* if it's available in the organic box and not a stub,
               switch index to it */
            olisting.find('.thing:visible').hide();
            thing.show();
          } else {
              /* either it's available in the organic box, but the
                 data there is a stub, or it's not available at
                 all. either way, we need a server round-trip */

              /* remove the stub if it's there */
              thing.remove();

              /* add a new stub */
              olisting.find('.thing:visible')
                  .before('<div class="thing id-'+current.what+' stub" style="display: none"></div');
              
              /* and ask the server to fill it in */
              $.request('fetch_links',
                        {links: [current.what],
                                show: current.what,
                                listing: olisting.attr('id')});
          }
        }
      }
      
      /* mark it in the list */
      $.things(current.what).addClass("last-clicked");

      /* and wipe the cookie */
      $.cookie_write({name: cookie, data: ""});
    }
  }
};

function login(elem) {
    if(cnameframe)
        return true;

    return post_user(this, "login");
};

function register(elem) {
    if(cnameframe)
        return true;
    return post_user(this, "register");
};

/***submit stuff***/
function fetch_title() {
    var url_field = $("#url-field");
    var error = url_field.find(".NO_URL");
    var status = url_field.find(".title-status");
    var url = $("#url").val();
    if (url) {
        status.show().text("loading...");
        error.hide();
        $.request("fetch_title", {url: url});
    }
    else {
        status.hide();
        error.show().text("a url is required");
    }
}

/**** sr completing ****/
function sr_cache() {
    if (!$.defined(reddit.sr_cache)) {
        reddit.sr_cache = new Array();
    }
    return reddit.sr_cache;
}

function highlight_reddit(item) {
    $("#sr-drop-down").children('.sr-selected').removeClass('sr-selected');
    if (item) {
        $(item).addClass('sr-selected');
    }
}

function update_dropdown(sr_names) {
    var drop_down = $("#sr-drop-down");
    if (!sr_names.length) {
        drop_down.hide();
        return;
    }

    var first_row = drop_down.children(":first");
    first_row.removeClass('sr-selected');
    drop_down.children().remove();

    $.each(sr_names, function(i) {
            if (i > 10) return;
            var name = sr_names[i];
            var new_row = first_row.clone();
            new_row.text(name);
            drop_down.append(new_row);
        });


    var height = $("#sr-autocomplete").outerHeight();
    drop_down.css('top', height);
    drop_down.show();
}

function sr_search(query) {
    query = query.toLowerCase();
    var cache = sr_cache();
    if (!cache[query]) {
        $.request('search_reddit_names', {query: query},
                  function (r) {
                      cache[query] = r['names'];
                      update_dropdown(r['names']);
                  });
    }
    else {
        update_dropdown(cache[query]);
    }
}

function sr_name_up(e) {
    var new_sr_name = $("#sr-autocomplete").val();
    var old_sr_name = window.old_sr_name || '';
    window.old_sr_name = new_sr_name;

    if (new_sr_name == '') {
        hide_sr_name_list();
    }
    else if (e.keyCode == 38 || e.keyCode == 40 || e.keyCode == 9) {
    }
    else if (e.keyCode == 27 && reddit.orig_sr) {
        $("#sr-autocomplete").val(reddit.orig_sr);
        hide_sr_name_list();
    }
    else if (new_sr_name != old_sr_name) {
        reddit.orig_sr = new_sr_name;
        sr_search($("#sr-autocomplete").val());
    }
}

function sr_name_down(e) {
    var input = $("#sr-autocomplete");
    
    if (e.keyCode == 38 || e.keyCode == 40) {
        var dir = e.keyCode == 38 && 'up' || 'down';

        var cur_row = $("#sr-drop-down .sr-selected:first");
        var first_row = $("#sr-drop-down .sr-name-row:first");
        var last_row = $("#sr-drop-down .sr-name-row:last");

        var new_row = null;
        if (dir == 'down') {
            if (!cur_row.length) new_row = first_row;
            else if (cur_row.get(0) == last_row.get(0)) new_row = null;
            else new_row = cur_row.next(':first');
        }
        else {
            if (!cur_row.length) new_row = last_row;
            else if (cur_row.get(0) == first_row.get(0)) new_row = null;
            else new_row = cur_row.prev(':first');
        }
        highlight_reddit(new_row);
        if (new_row) {
            input.val($.trim(new_row.text()));
        }
        else {
            input.val(reddit.orig_sr);
        }
        return false;
    }
    else if (e.keyCode == 13) {
        hide_sr_name_list();
        input.parents("form").submit();
        return false;
    }   
}

function hide_sr_name_list(e) {
    $("#sr-drop-down").hide();
}

function sr_dropdown_mdown(row) {
    reddit.sr_mouse_row = row; //global
    return false;
}

function sr_dropdown_mup(row) {
    if (reddit.sr_mouse_row == row) {
        var name = $(row).text();
        $("#sr-autocomplete").val(name);
        $("#sr-drop-down").hide();
    }
}

function set_sr_name(link) {
    var name = $(link).text();
    $("#sr-autocomplete").trigger('focus').val(name);
}

/*** tabbed pane stuff ***/
function select_form_tab(elem, to_show, to_hide) {
    //change the menu    
    var link_parent = $(elem).parent();
    link_parent
        .addClass('selected')
        .siblings().removeClass('selected');
    
    //swap content and enable/disable form elements
    var content = link_parent.parent('ul').next('.formtabs-content');
    content.find(to_show)
        .show()
        .find(":input").removeAttr("disabled").end();
    content.find(to_hide)
        .hide()
        .find(":input").attr("disabled", true);
}

/**** expando stuff ********/
function expando_cache() {
    if (!$.defined(reddit.thing_child_cache)) {
        reddit.thing_child_cache = new Array();
    }
    return reddit.thing_child_cache;
}

function expando_child(elem) {
    var child_cache = expando_cache();
    var thing = $(elem).thing();

    //swap button
    var button = thing.find(".expando-button");
    button
        .addClass("expanded")
        .removeClass("collapsed")
        .get(0).onclick = function() {unexpando_child(elem)};

    //load content
    var expando = thing.find(".expando");
    var key = thing.thing_id() + "_cache";
    if (!child_cache[key]) {
        $.request("expando",
                  {"link_id":thing.thing_id()},
                  function(r) {
                      child_cache[key] = r;
                      expando.html($.unsafe(r));
                  },
                  false, "html");
    }
    else {
        expando.html($.unsafe(child_cache[key]));
    }
    expando.show();
}

function unexpando_child(elem) {
    var thing = $(elem).thing();
    var button = thing.find(".expando-button");
    button
        .addClass("collapsed")
        .removeClass("expanded")
        .get(0).onclick = function() {expando_child(elem)};

    thing.find(".expando").hide().empty();
}

/******* editting comments *********/
function show_edit_usertext(form) {
    var edit = form.find(".usertext-edit");
    var body = form.find(".usertext-body");
    var textarea = edit.find('div > textarea');

    //max of the height of the content or the min values from the css.
    var body_width = Math.max(body.children(".md").width(), 500);
    var body_height = Math.max(body.children(".md").height(), 100);

    //we need to show the textbox first so it has dimensions
    body.hide();
    edit.show();

    //restore original (?) css width/height. I can't explain why, but
    //this is important.
    textarea.css('width', '');
    textarea.css('height', '');

    //if there would be scroll bars, expand the textarea to the size
    //of the rendered body text
    if (textarea.get(0).scrollHeight > textarea.height()) {
        var new_width = Math.max(body_width - 5, textarea.width());
        textarea.width(new_width);
        edit.width(new_width);

        var new_height = Math.max(body_height, textarea.height());
        textarea.height(new_height);
    }

    form
        .find(".cancel, .save").show().end()
        .find(".help-toggle").show().end();

    textarea.focus();
}

function hide_edit_usertext(form) {
    form
        .find(".usertext-edit").hide().end()
        .find(".usertext-body").show().end()
        .find(".cancel, .save").hide().end()
        .find(".help-toggle").hide().end()
        .find(".markhelp").hide().end()
}

function comment_reply_for_elem(elem) {
    elem = $(elem);
    var thing = elem.thing();
    var thing_id = elem.thing_id();
    //try to find a previous form
    var form = thing.find(".child .usertext:first");
    if (!form.length || form.parent().thing_id() != thing.thing_id()) {
        form = $(".usertext.cloneable:first").clone(true);
        elem.new_thing_child(form);
        form.attr("thing_id").value = thing_id;
        form.attr("id", "commentreply_" + thing_id);
        form.find(".error").hide();
    }
    return form;
}

function edit_usertext(elem) {
    show_edit_usertext($(elem).thing().find(".usertext:first"));
}

function cancel_usertext(elem) {
    hide_edit_usertext($(elem).thing().find(".usertext:first"));
}

function save_usertext(elem) {
}

function reply(elem) {
    var form = comment_reply_for_elem(elem);
    //show the right buttons
    show_edit_usertext(form);
    //re-show the whole form if required
    form.show();
    //update the cancel button to call the toggle button's click
    form.find(".cancel").get(0).onclick = function() {form.hide()};
}

function toggle_distinguish_span(elem) {
  var form = $(elem).parents("form")[0];
  $(form).children().toggle();
}

function set_distinguish(elem, value) {
  change_state(elem, "distinguish/" + value);
  $(elem).children().toggle();
}

function populate_click_gadget() {
    /* if we can find the click-gadget, populate it */
    if($('.click-gadget').length) {
        var clicked = clicked_items();

        if(clicked && clicked.length) {
            clicked = $.uniq(clicked, 5);
            clicked.sort();

            $.request('gadget/click/' + clicked.join(','), undefined, undefined,
                      undefined, "json", true);
        }
    }
}

var toolbar_p = function(expanded_size, collapsed_size) {
    /* namespace for functions related to the reddit toolbar frame */

    this.toggle_linktitle = function(s) {
        $('.title, .submit, .url, .linkicon').toggle();
        if($(s).is('.pushed-button')) {
            $(s).parents('.middle-side').removeClass('clickable');
        } else {
            $(s).parents('.middle-side').addClass('clickable');
            $('.url').children('form').children('input').focus().select();
        }
        return this.toggle_pushed(s);
    };

    this.toggle_pushed = function(s) {
        s = $(s);
        if(s.is('.pushed-button')) {
            s.removeClass('pushed-button').addClass('popped-button');
        } else {
            s.removeClass('popped-button').addClass('pushed-button');
        }
        return false;
    };

    this.push_button = function(s) {
        $(s).removeClass("popped-button").addClass("pushed-button");
    };

    this.pop_button = function(s) {
        $(s).removeClass("pushed-button").addClass("popped-button");
    };
    
    this.serendipity = function() {
        this.push_button('.serendipity');
        return true;
    };
    
    this.show_panel = function() {
        parent.inner_toolbar.document.body.cols = expanded_size;
    };
        
    this.hide_panel = function() {
        parent.inner_toolbar.document.body.cols = collapsed_size;
    };
        
    this.resize_toolbar = function() {
        var height = $("body").height();
        parent.document.body.rows = height + "px, 100%";
    };
        
    this.login_msg = function() {
        $(".toolbar-status-bar").show();
        $(".login-arrow").show();
        this.resize_toolbar();
        return false;
    };
        
    this.top_window = function() {
        var w = window;
        while(w != w.parent) {
            w = w.parent;
        }
        return w.parent;
    };
        
    var pop_obj = null;
    this.panel_loadurl = function(url) {
        try {
            var cur = window.parent.inner_toolbar.reddit_panel.location;
            if (cur == url) {
                return false;
            } else {
                if (pop_obj != null) {
                    this.pop_button(pop_obj);
                    pop_obj = null;
                }
                return true;
            }
        } catch (e) {
            return true;
        }
    };
        
    var comments_on = 0;
    this.comments_pushed = function(ctl) {
        comments_on = ! comments_on;
        
        if (comments_on) {
            this.push_button(ctl);
            this.show_panel();
        } else {
            this.pop_button(ctl);
            this.hide_panel();
        }
    };
    
    this.gourl = function(form, base_url) {
        var url = $(form).find('input[type=text]').attr('value');
        var newurl = base_url + escape(url);
        
        this.top_window().location.href = newurl;
        
        return false;
    };

    this.pref_commentspanel_hide = function() {
        $.request('tb_commentspanel_hide');
    };
    this.pref_commentspanel_show = function() {
        $.request('tb_commentspanel_show');
    };
};

function clear_all_langs(elem) {
    $(elem).parents("form").find("input[type=checkbox]").attr("checked", false);
}

function check_some_langs(elem) {
    $(elem).parents("form").find("#some-langs").attr("checked", true);
}

/* The ready method */
$(function() {
        /* set function to be called on thing creation/replacement,
         * and call it on all things currently rendered in the
         * page. */
        $("body").set_thing_init(updateEventHandlers);
        
        /* Set up gray inputs and textareas to clear on focus */
        $("textarea.gray, input.gray")
            .focus( function() {
                    $(this).attr("rows", 7)
                        .filter(".gray").removeClass("gray").attr("value", "")
                        });
        /* set cookies to be from this user if there is one */
        if (reddit.logged) {
            $.cookie_name_prefix(reddit.logged);
        }
        else {
            //populate_click_gadget();
        }
        /* set up the cookie domain */
        $.default_cookie_domain(reddit.cur_domain.split(':')[0]);
        
        /* Count the rendering of this reddit */
        if(reddit.cur_site)  
           update_reddit_count(reddit.cur_site);

        /* visually mark the last-clicked entry */
        last_click();


    });
