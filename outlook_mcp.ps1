# Read-only Outlook adapter. Uses an existing local profile; never asks for a password.
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$request = [Console]::In.ReadToEnd() | ConvertFrom-Json
$outlook = New-Object -ComObject Outlook.Application
$session = $outlook.GetNamespace('MAPI')
switch ($request.tool) {
    'outlook_status' {
        $result = @{ storeCount = $session.Stores.Count; inboxAccessible = ($null -ne $session.GetDefaultFolder(6)); calendarAccessible = ($null -ne $session.GetDefaultFolder(9)) }
    }
    'outlook_inbox' {
        $limit = 20
        if ($null -ne $request.arguments.limit) { $limit = [int]$request.arguments.limit }
        if ($limit -lt 1 -or $limit -gt 50) { throw 'Choose between one and fifty messages.' }
        $folder = $session.GetDefaultFolder(6)
        $items = $folder.Items
        $items.Sort('[ReceivedTime]', $true)
        $result = @(for ($i = 1; $i -le [Math]::Min($limit, $items.Count); $i++) {
            $message = $items.Item($i)
            @{ entry_id = $message.EntryID; store_id = $folder.StoreID; subject = $message.Subject; sender = $message.SenderName; received = [string]$message.ReceivedTime }
        })
    }
    'outlook_read' {
        $entry = [string]$request.arguments.entry_id
        $store = [string]$request.arguments.store_id
        if (-not $entry -or -not $store -or $entry.Length -gt 4096 -or $store.Length -gt 4096) { throw 'Choose a message returned by outlook_inbox.' }
        $message = $session.GetItemFromID($entry, $store)
        $body = [string]$message.Body
        $result = @{ subject = $message.Subject; sender = $message.SenderName; received = [string]$message.ReceivedTime; body = $body.Substring(0, [Math]::Min(16000, $body.Length)); truncated = ($body.Length -gt 16000) }
    }
    'outlook_calendar' {
        $days = 7
        if ($null -ne $request.arguments.days) { $days = [int]$request.arguments.days }
        if ($days -lt 1 -or $days -gt 31) { throw 'Choose between one and thirty-one days.' }
        $start = (Get-Date).Date
        $end = $start.AddDays($days)
        $items = $session.GetDefaultFolder(9).Items
        $items.Sort('[Start]')
        $items.IncludeRecurrences = $true
        $format = [Globalization.CultureInfo]::InvariantCulture
        $filter = "[Start] < '" + $end.ToString('MM/dd/yyyy HH:mm', $format) + "' AND [End] > '" + $start.ToString('MM/dd/yyyy HH:mm', $format) + "'"
        $matches = $items.Restrict($filter)
        $result = @()
        $item = $matches.GetFirst()
        while ($null -ne $item -and $result.Count -lt 100) {
            $result += @{ subject = $item.Subject; start = $item.Start.ToString('o'); end = $item.End.ToString('o'); location = $item.Location }
            $item = $matches.GetNext()
        }
    }
    default { throw 'Unknown read-only Outlook tool.' }
}
ConvertTo-Json -InputObject $result -Depth 6 -Compress
