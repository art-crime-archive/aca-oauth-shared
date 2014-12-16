

$(document).ready(function () {
    // automatically get and show more content when user scrolls to end of page
    $(window).scroll(function() {
        console.log('scrolling');
        var totalHeight, currentScroll, visibleHeight;        
        currentScroll = $(document).scrollTop();
        totalHeight = document.body.offsetHeight;
        visibleHeight = document.documentElement.clientHeight;
        if (visibleHeight + currentScroll + 10 >= totalHeight) {
              // get more content when user scrolls to bottom
              console.log('end?=', $('#bookmark-end').length);
            if (window.location.pathname == '/the-archive' && $('div[id^="the-archive"] > .bookmark-end').length == 0) {
              var url =   window.location.href + '?bookmark=' + encodeURIComponent($('.bookmark:last').attr('data-bookmark'));
              loadAjaxContent('#content', url, '#the-archive-next');
			}
            if (window.location.pathname == '/recent' && $('div[id^="the-archive"] > .bookmark-end').length == 0) {
              var url =   window.location.href + '?bookmark=' + encodeURIComponent($('.bookmark:last').attr('data-bookmark'));
              loadAjaxContent('#content', url, '#recent-next');
// lAC target = #content   sel= #the-archive 
            }
            console.log('scrolled to end');
        }
    });
    $.ajax ({
        url: "/ArchiveService.get_articles_by_date",
        type: "POST",
        data: JSON.stringify({}),
        dataType: "json",
        contentType: "application/json; charset=utf-8",
        success: function(data) {
            // copy hidden comment row before modifying with new comment
			console.log('get_articles_by_date: ', data.articles);
			for (var article in data.articles) {
				$('#test').append(data.articles[article].embed);
				console.log(data.articles[article].embed);
			}
        }
    });
  var ajaxContentReady = function () {
    console.log('contentReady');
    $(".comment-text").hint({text:"add your comment..."});
    // Fits videos in fluid grid
    $(".center-stage").fitVids({ customSelector: "object[src^='/']"});
    // autosize and autobuttons for comment boxes
    $('.comment-text').autosize({append: "\n"});
  };

  ajaxContentReady();

  // If signed in, append a publish comment button when comment text is clicked.
  $('body').on('focus', 'tfoot .comment-text', function(e) {
    var form = $(this).parent();
    console.log('signed in? ', $('#not-signed-in').length)
    if (!form.find('input').length) {
      if ($('#not-signed-in').length) {
        window.location = $('#not-signed-in').attr('href') + '%23' + $(this).attr('id');
      }
      else {
        $(form).append('<div><input class="publish" id="publish-it" type="submit" value="Publish Comment" /></div>');
      }
    }
  });
  $('body').on('blur', '.comment-text', function(e) {
    var form = $(this).parent()
    if ($(this).val().trim() == '') {
        // user did not add comment, remove the div with publish comment button
      $(form.find('div')).remove();
    }
  });
  var updateNav = function(urlPath) {
  $('a[href="' + urlPath + '"]').parent().addClass('active').siblings('.active').removeClass('active');
  };

  // History.js - HTML5 History API handling 
  var History = window.History;
  if (History.enabled) {
      State = History.getState();
      // set initial state to first page that was loaded
      console.log(window.location.pathname);
      History.pushState({urlPath: window.location.pathname}, $("title").text(), State.urlPath);
      updateNav(window.location.pathname);
  } else {
      return false;
  }

var loadAjaxContent = function(target, urlBase, selector) {
    $('#ajax_content').load(urlBase + ' ' + selector, function(response, status, xhr) {
        if (status == "error") {
          var msg = '<div id="' + selector.slice(1) + '">You must <a href="' + $('#not-signed-in').attr('href') + '">Sign in or register</a> to use this feature</div>';
          $('#ajax_content').html(msg);
        }
        $(selector).appendTo(target).siblings().addClass('hidden');
        console.log('div[id^="' + selector.slice(1, -5) + '"]', '-next?=', selector.match("-next$") == '-next');
        if (selector.match("-next$") == '-next') {
            $(selector.slice(0, -5)).removeClass('hidden');
            $($(selector).contents()).appendTo(selector.slice(0, -5));
            $(selector).remove();
        }
        ajaxContentReady();
        console.log('lAC', target,' ', urlBase, 'sel=', selector);
    });
};

function addslashes( str ) {
    return (str+'').replace(/([\\"'])/g, "\\$1").replace(/\0/g, "\\0");
}
var updateContent = function(State) {
    // uses the path with cleaned up query string as the selector
    var selector = ('#' + State.data.urlPath.substring(1).replace(/[?=&%]/g,"-"));
//    var selector = ('#' + State.data.urlPath.substring(1)).split('?')[0];
    console.log('url=', State.url,' selector=', selector);
    if ($(selector).length) { //content is already loaded but hidden
        $(selector).siblings().addClass('hidden');
        $(selector).removeClass('hidden');
    } else {
        loadAjaxContent('#content', State.url, selector);
    }
};

  // Content update and back/forward button handler
  History.Adapter.bind(window, 'statechange', function() {
  console.log('HAb');
      updateNav(window.location.pathname);
  console.log('after editAF ', History.getState());
      updateContent(History.getState());
  });

  // navigation link handler
  $('body').on('click', 'a:not([href^="/edit-article-form?"], .btn, .no-ajax)', function(e) {
   console.log('Navlink');
      var urlPath = $(this).attr('href');
      var title = $(this).text();
      History.pushState({urlPath: urlPath}, title, urlPath);
      return false; // prevents default click action of <a ...>
  });
  // edit article
  $('body').on('click', 'a[href^="/edit-article-form?"]', function(e) {
      var urlPath = $(this).attr('href');
      var title = $(this).text();
//      var selector = '\/edit-article-form\?id\=13006'
//      var selector = ('#' + urlPath.substring(1)).split('?')[0];
//    console.log('editAF urlPath=', urlPath, 'sel=', selector, 'title=', title);
      // use loadAjaxContent instead
//        loadAjaxContent('#content', urlPath, selector);
      updateNav('/my-articles');
      History.pushState({urlPath: urlPath}, title, urlPath);
      return false; // prevents default click action of <a ...>
  });
  // edit comment
  $('body').on('mouseenter', '.comment', function(){
      var user = $('.signed-in').attr('nickname').split('@')[0];
      var comment_author = $(this).attr('author');
      if (user == comment_author){
        $(this).css( 'cursor', 'pointer' );
      }
  });
  // helps .on submit detect which button was pressed
  $('body').on('click', 'input[type=submit]', function(e) {
        console.log($(this));
        $(this.form).data('clicked', this.value);
  });
  $('body').on('click', '.comment', function(){
      // create and show comment-edit form if comment is by signed in user
      var user = $('.signed-in').attr('nickname').split('@')[0];
      var comment_author = $(this).attr('author');
        console.log('in .comment', $(this));
      if (user == comment_author){
        var $comment_edit = $('.comment-add-' + $(this).attr('article')).clone();
        $comment_edit.attr('class', 'comment-edit');
        $comment_edit.insertAfter($(this));
        $comment_edit.find('div').remove();
        previous_comment = $(this).find('span[class="comment-display"]').text();
        $comment_edit.find('.comment-text').val(previous_comment);
        $comment_edit.find('.comment-text').attr('title', previous_comment);
        $comment_edit.find('.comment-form').attr('comment-id', $(this).attr('comment-id'));
        $comment_edit.find('.comment-form').attr('name', 'comment-edit-form');
        $comment_edit.find('.comment-form').attr('class', 'comment-edit-form');
        $(this).attr('class', 'comment hidden');
        $(this).next().find('textarea').focus();
        $(this).next().find('textarea').click();
      }
  });
  $('body').on('click', '.comment-edit', function(){
      // user has clicked into edit comment
        console.log('in .comment-edit', $(this).find('input[class="publish"]').length);
      if (!$(this).find('input[class="publish"]').length) {
          $(this).find('.comment-edit-form').append('<div><input class="publish" id="publish-it" name="update" type="submit" value="Update" style="display: inline;" /><input class="publish" name="update" id="delete-it" type="submit" value="Delete" style="display: inline;"/></div>');
       }
  });
  $('body').on('mouseleave', '.comment-edit', function(){
      if ($(this).find('textarea').attr('title') == $(this).find('textarea').val()) {
        $(this).prev().attr('class', 'comment');
        $(this).remove();
      }
  });
  $('body').on('submit', '.comment-form', function(e) {
    var article_id = $(this).attr('article');
    var $textarea = $(this).find('textarea');
    var text = $textarea.val();
    $.ajax ({
        url: "/ArchiveService.post_comment",
        type: "POST",
        data: JSON.stringify({"article_id": article_id, "comment_text": text}),
        dataType: "json",
        contentType: "application/json; charset=utf-8",
        success: function(data) {
            // copy hidden comment row before modifying with new comment
            var $clone = $('#comment-' + article_id).clone();
        console.log('clone= ', $clone);
            $('#comment-table-' + article_id).append($clone);
            // fill in and unhide new comment row
            new_comment_id = 'comment-' + article_id + '-' + data.comment_id
        console.log('new_comment_id= ', new_comment_id);
            $('#comment-' + article_id).attr('id', new_comment_id);
            $('#' + new_comment_id).find('span[class="comment-display"]').text(text);
            $('#' + new_comment_id).find('a[class="comment-user"]').attr(data.user_url);
            $('#' + new_comment_id).find('a[class="comment-user"]').text(data.nickname.split('@')[0]);
            $('#' + new_comment_id).attr('comment-id', data.comment_id);
            $('#' + new_comment_id).attr('author', data.nickname.split('@')[0]);
            $('#' + new_comment_id).attr('class', 'comment');
        }
    });
    // reset comment form
    $textarea.val('add your comment...');
    $($(this).find('div')).remove();
    return false;
  });
  $('body').on('submit', '.comment-edit-form', function(e) {
    var article_id = $(this).attr('article');
    var comment_id = $(this).attr('comment-id');
    var $textarea = $(this).find('textarea');
    var text = $textarea.val();
    if ($(this).data('clicked') == "Update") {
        $.ajax ({
            url: "/ArchiveService.edit_comment",
            type: "POST",
            data: JSON.stringify({"article_id": article_id, 
                                  "comment_text": text, 
                                  "comment_id": comment_id}),
            dataType: "json",
            contentType: "application/json; charset=utf-8",
            success: function(data) {
                // update and unhide edited comment
                new_comment_id = 'comment-' + article_id + '-' + comment_id;
                $('#' + new_comment_id).find('span[class="comment-display"]').text(text);
                $('#' + new_comment_id).find('span[class="comment-relativetime"]').text('0 minutes ago');
                $('#' + new_comment_id).attr('class', 'comment');
                $('#' + new_comment_id).next().remove();
            }
        });
    }
    if ($(this).data('clicked') == "Delete") {
        console.log('in delete');
        $.ajax ({
            url: "/ArchiveService.delete_comment",
            type: "POST",
            data: JSON.stringify({"article_id": article_id, 
                                  "comment_text": '', 
                                  "comment_id": comment_id}),
            dataType: "json",
            contentType: "application/json; charset=utf-8",
            success: function(data) {
                // update and hide deleted comment row
                deleted_comment_id = 'comment-' + article_id + '-' + comment_id;
                $('#' + deleted_comment_id).attr('class', 'comment deleted');
                $('#' + deleted_comment_id).next().remove();
                
            }
        });
    }
    return false;
  });
});
